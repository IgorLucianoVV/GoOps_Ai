"""Motor de Data Quality com regras declarativas e versionadas.

Severidades:
  * error   -> o registro vai para QUARENTENA (não avança para a Silver), com rastreabilidade.
  * warning -> o registro avança, sinalizado em `_dq_flags`.
  * info    -> apenas medição.
Regras são funções controladas (sem execução de código arbitrário vindo de usuários).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple

import pandas as pd

UFS = {"AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
       "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"}


@dataclass(frozen=True)
class Rule:
    key: str
    dataset: str
    description: str
    severity: str
    version: str
    check: Callable[[pd.DataFrame], pd.Series]  # retorna máscara True = falhou


def _cast_failed(field: str) -> Callable[[pd.DataFrame], pd.Series]:
    return lambda df: df["_cast_errors"].map(lambda e: field in (e or {}))


ROW_RULES: List[Rule] = [
    Rule("orders_order_id_required", "silver_orders", "Identificador do pedido (Order ID) obrigatório", "error", "1.0",
         lambda df: df["order_id"].isna()),
    Rule("orders_order_date_valid", "silver_orders", "Data do pedido presente e válida", "error", "1.0",
         lambda df: df["order_date"].isna()),
    Rule("orders_total_non_negative", "silver_orders", "Valor do pedido numérico e não negativo", "warning", "1.0",
         lambda df: df["order_total"].isna() | (df["order_total"] < 0)),
    Rule("orders_state_valid", "silver_orders", "UF válida quando informada", "warning", "1.1",
         lambda df: df["state"].notna() & ~df["state"].isin(UFS)),
    Rule("nps_evaluation_id_required", "silver_nps_evaluations", "Identificador da avaliação obrigatório", "error", "1.0",
         lambda df: df["evaluation_id"].isna()),
    Rule("nps_order_id_required", "silver_nps_evaluations", "Código do Pedido obrigatório (exigido pela fonte)",
         "error", "1.0", lambda df: df["order_id"].isna()),
    Rule("nps_score_range", "silver_nps_evaluations", "Nota NPS inteira entre 0 e 10", "error", "1.0",
         lambda df: df["score"].isna() | ~df["score"].between(0, 10) | _cast_failed("score")(df)),
    Rule("nps_evaluation_date_valid", "silver_nps_evaluations", "Data da avaliação presente e válida", "error", "1.0",
         lambda df: df["evaluation_date"].isna()),
    Rule("deliveries_order_id_required", "silver_deliveries", "reference (pedido) obrigatório", "error", "1.0",
         lambda df: df["order_id"].isna()),
    Rule("deliveries_dates_coherent", "silver_deliveries", "Data de entrega não pode ser anterior ao envio", "error",
         "1.0", lambda df: df["actual_delivery_date"].notna() & df["shipping_date"].notna()
         & (df["actual_delivery_date"] < df["shipping_date"])),
    Rule("deliveries_carrier_identified", "silver_deliveries", "Transportadora identificável quando houve envio",
         "warning", "1.0", lambda df: df["carrier"].isna() & df["shipping_date"].notna()),
    Rule("deliveries_state_valid", "silver_deliveries", "UF de entrega reconhecida quando informada", "warning", "1.0",
         lambda df: df["_cast_errors"].map(lambda e: "state" in (e or {}))),
    Rule("deliveries_days_valid", "silver_deliveries", "Dias de entrega não negativos quando informados", "warning", "1.0",
         lambda df: df["delivery_days"].notna() & (df["delivery_days"] < 0)),
    Rule("deliveries_dates_parseable", "silver_deliveries", "Datas de envio/previsão/entrega válidas quando informadas",
         "warning", "1.0", lambda df: df["_cast_errors"].map(
             lambda e: any(k in (e or {}) for k in ("shipping_date", "estimated_delivery_date", "actual_delivery_date")))),
]

# Regras calculadas fora do motor de linhas (deduplicação e relacionamentos) — registradas para catálogo.
META_RULES = [
    ("orders_exact_duplicates", "silver_orders", "Registros de pedido duplicados (mesmo payload)", "warning"),
    ("orders_version_conflicts", "silver_orders", "Mesmo Order ID com conteúdos diferentes na mesma execução", "warning"),
    ("nps_exact_duplicates", "silver_nps_evaluations", "Avaliações duplicadas (mesmo payload)", "warning"),
    ("nps_version_conflicts", "silver_nps_evaluations", "Mesma avaliação com conteúdos diferentes na mesma execução", "warning"),
    ("deliveries_exact_duplicates", "silver_deliveries", "Entregas duplicadas (mesmo payload)", "warning"),
    ("deliveries_version_conflicts", "silver_deliveries", "Mesma entrega com conteúdos diferentes", "warning"),
    ("ids_numeric_type", "*", "Identificador recebido como número (risco de perda de zeros à esquerda)", "warning"),
    ("nps_orphan_evaluation", "silver_nps_evaluations", "Avaliação sem pedido correspondente", "warning"),
    ("deliveries_orphan", "silver_deliveries", "Entrega sem pedido correspondente", "warning"),
    ("orders_without_evaluation", "silver_orders", "Pedidos sem avaliação (medição)", "info"),
]


def run_row_rules(df: pd.DataFrame, dataset: str, record_key: str) -> Tuple[pd.DataFrame, pd.DataFrame, List[Dict]]:
    """Aplica regras de linha. Retorna (válidos, quarentena, resultados)."""
    rules = [r for r in ROW_RULES if r.dataset == dataset]
    results: List[Dict] = []
    error_reasons = pd.Series([[] for _ in range(len(df))], index=df.index, dtype=object)
    warn_flags = pd.Series([[] for _ in range(len(df))], index=df.index, dtype=object)
    for rule in rules:
        mask = rule.check(df).fillna(False).astype(bool) if len(df) else pd.Series([], dtype=bool)
        failed = int(mask.sum())
        target = error_reasons if rule.severity == "error" else warn_flags
        for idx in df.index[mask]:
            target.at[idx] = target.at[idx] + [rule.key]
        sample = [str(v) for v in df.loc[mask, record_key].head(5).tolist()] if failed else []
        results.append({"rule_key": rule.key, "dataset": dataset, "severity": rule.severity,
                        "rule_version": rule.version, "checked": int(len(df)), "failed": failed,
                        "status": "passed" if failed == 0 else ("failed" if rule.severity == "error" else "warning"),
                        "sample": sample})
    is_error = error_reasons.map(bool)
    out = df.copy()
    out["_dq_flags"] = warn_flags.map(lambda v: "|".join(v) if v else None)
    quarantined = out[is_error].copy()
    quarantined["_reasons"] = error_reasons[is_error].map(lambda v: "|".join(v))
    return out[~is_error].copy(), quarantined, results


def meta_result(rule_key: str, dataset: str, severity: str, checked: int, failed: int, sample: List[str]) -> Dict:
    return {"rule_key": rule_key, "dataset": dataset, "severity": severity, "rule_version": "1.0",
            "checked": int(checked), "failed": int(failed),
            "status": "passed" if failed == 0 else ("info" if severity == "info" else "warning"),
            "sample": [str(s) for s in sample[:5]]}
