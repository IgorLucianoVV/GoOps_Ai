"""Módulo analítico de NPS.

TODOS os indicadores usam a métrica governada METRIC_NPS_001 (e métricas corporativas
relacionadas) via semantic.registry.compute_metric. Nenhuma fórmula é recalculada no frontend.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from goops_core.db import Database
from goops_core.errors import ValidationError
from goops_core.permissions import Principal, require_permission
from goops_core.util import to_jsonable

from ..catalog import get_dataset
from ..semantic.registry import compute_metric, get_metric, load_dataset_frame
from ..semantic.engine import apply_filters
from ..storage import Lakehouse
from .nlp import frequencies
from .stats import correlation, strength_label

NPS_KEY = "METRIC_NPS_001"
FILTER_DIMS = ("state", "product_line", "carrier", "shipping_type")
LOW_SAMPLE = 30
UNLINKED = "Não identificado"          # rótulo do motor semântico para dimensão nula (compute_grouped)
UNLINKED_LABEL = "Sem vínculo com pedido"


class NpsAnalytics:
    def __init__(self, db: Database, lake: Lakehouse, actor: Principal):
        require_permission(actor, "analytics:read")
        self.db, self.lake, self.actor = db, lake, actor

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def clean_filters(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k, v in (raw or {}).items():
            if v in (None, "", []):
                continue
            if k not in ("start", "end") + FILTER_DIMS:
                raise ValidationError(f"Filtro não suportado: {k}")
            out[k] = v
        return out

    def _metric(self, filters: Dict[str, Any], group_by: Optional[str] = None, key: str = NPS_KEY) -> Dict[str, Any]:
        return compute_metric(self.db, self.lake, self.actor, key, filters, group_by)

    def frame(self, filters: Dict[str, Any]) -> pd.DataFrame:
        """Mesmo recorte aplicado pelo motor semântico (filtros da métrica + filtros do usuário)."""
        m = get_metric(self.db, NPS_KEY)
        df = apply_filters(load_dataset_frame(self.db, self.lake, m["source_datasets"][0]), m["filters"])
        tf = m["formula_definition"]["time_field"]
        for k, v in filters.items():
            if k == "start":
                df = df[df[tf] >= pd.to_datetime(v)]
            elif k == "end":
                df = df[df[tf] < pd.to_datetime(v) + pd.Timedelta(days=1)]
            else:
                df = df[df[k].isin(v if isinstance(v, list) else [v])]
        return df

    def _meta(self, extra: Optional[dict] = None) -> dict:
        ds = get_dataset(self.db, "gold_nps_analytics")
        return {"dataset": "gold_nps_analytics", "dataset_built_at": ds["last_built_at"], "is_demo": ds["is_demo"],
                "pipeline_run_id": ds["last_pipeline_run_id"], **(extra or {})}

    # ---------------------------------------------------------------- indicadores
    def overview(self, filters: Optional[dict] = None) -> dict:
        f = self.clean_filters(filters)
        nps = self._metric(f)
        invalid = self.db.fetchone("SELECT failed FROM dq_results WHERE rule_key = 'nps_score_range' "
                                   "ORDER BY executed_at DESC LIMIT 1")
        return {"nps": nps["result"], "metric": nps["metric"],
                "invalid_scores_quarantined": invalid["failed"] if invalid else None, "meta": self._meta()}

    def evolution(self, filters: Optional[dict] = None) -> dict:
        f = self.clean_filters(filters)
        res = self._metric(f, "eval_month")
        groups = {g["eval_month"]: g for g in res["groups"] if g["eval_month"] != UNLINKED}
        rows: List[dict] = []
        if groups:
            months = pd.period_range(min(groups), max(groups), freq="M").strftime("%Y-%m")
            prev_value = None
            for m in months:
                g = groups.get(m)
                if g is None or g["n"] == 0:
                    rows.append({"month": m, "total": 0, "promoters": 0, "neutrals": 0, "detractors": 0,
                                 "nps": None, "delta": None, "has_data": False})
                    continue
                delta = None if prev_value is None else round(g["value"] - prev_value, 2)
                rows.append({"month": m, "total": g["n"], "promoters": g["promoters"], "neutrals": g["neutrals"],
                             "detractors": g["detractors"], "nps": g["value"], "delta": delta, "has_data": True,
                             "low_sample": g["n"] < LOW_SAMPLE})
                prev_value = g["value"]
        return {"rows": rows, "metric": res["metric"], "meta": self._meta(
            {"note": "Meses sem avaliações são exibidos com NPS nulo (não zero). Delta vs. mês anterior com dados."})}

    def distribution(self, filters: Optional[dict] = None) -> dict:
        f = self.clean_filters(filters)
        df = self.frame(f)
        counts = df["score"].value_counts().reindex(range(0, 11), fill_value=0)
        res = self._metric(f)["result"]
        return {"scores": [{"score": int(s), "count": int(c), "category": "promoter" if s >= 9 else
                            ("neutral" if s >= 7 else "detractor")} for s, c in counts.items()],
                "categories": {"promoters": res["promoters"], "neutrals": res["neutrals"], "detractors": res["detractors"],
                               "promoter_pct": res["promoter_pct"], "neutral_pct": res["neutral_pct"],
                               "detractor_pct": res["detractor_pct"], "total": res["n"]},
                "meta": self._meta()}

    def by_dimension(self, dimension: str, filters: Optional[dict] = None) -> dict:
        if dimension not in FILTER_DIMS:
            raise ValidationError(f"Dimensão inválida: {dimension}")
        f = self.clean_filters(filters)
        nps = self._metric(f, dimension)
        avg = {g[dimension]: g["value"] for g in self._metric(f, dimension, "METRIC_AVG_SCORE_001")["groups"]}
        rows = []
        for g in nps["groups"]:
            rows.append({"value": g[dimension], "total": g["n"], "nps": g["value"], "detractor_rate": g["detractor_pct"],
                         "promoter_rate": g["promoter_pct"], "avg_score": avg.get(g[dimension]),
                         "low_sample": g["n"] < LOW_SAMPLE, "unlinked": g[dimension] == UNLINKED})
        # Segmentos reais ordenados por NPS; o grupo sem vínculo (avaliações órfãs ou sem atributo) vai por último:
        # não é um segmento de negócio e não deve ser lido como "pior estado/produto". Continua na lista para que
        # a soma dos grupos feche com o total.
        rows.sort(key=lambda r: (r["unlinked"], r["nps"] is None, r["nps"] if r["nps"] is not None else 0))
        unl = next((r for r in rows if r["unlinked"]), None)
        unlinked = None if unl is None else {
            "total": unl["total"], "nps": unl["nps"], "label": UNLINKED_LABEL,
            "note": "Avaliações sem pedido vinculado (órfãs) ou sem este atributo no pedido. Não representam um "
                    "segmento de negócio; ver Qualidade de dados › nps_orphan_evaluation."}
        return {"dimension": dimension, "rows": rows, "metric": nps["metric"],
                "meta": self._meta({"low_sample_threshold": LOW_SAMPLE, "unlinked": unlinked})}

    def correlation(self, filters: Optional[dict] = None) -> dict:
        f = self.clean_filters(filters)
        df = self.frame(f)
        out = {}
        row = self.db.fetchone("SELECT synthetic_fields FROM datasets WHERE key = 'gold_nps_analytics'")
        from goops_core.util import jload
        synthetic = set(jload(row["synthetic_fields"], []) or []) if row else set()
        for key, col, label in (("order_to_delivery", "lead_time_order_to_delivery_days", "Prazo pedido → entrega"),
                                ("ship_to_delivery", "lead_time_ship_to_delivery_days", "Prazo envio → entrega")):
            p = correlation(df[col], df["score"], "pearson")
            s = correlation(df[col], df["score"], "spearman")
            sub = df[[col, "score"]].dropna()
            buckets = []
            if len(sub):
                bins = [-0.01, 3, 5, 7, 10, 15, 1000]
                labels = ["0-3d", "3-5d", "5-7d", "7-10d", "10-15d", "15d+"]
                sub = sub.assign(bucket=pd.cut(sub[col], bins=bins, labels=labels))
                for b, part in sub.groupby("bucket", observed=False):
                    n = len(part)
                    nps = round(((part["score"] >= 9).sum() - (part["score"] <= 6).sum()) / n * 100, 2) if n else None
                    buckets.append({"bucket": str(b), "n": n, "nps": nps, "avg_score": round(float(part["score"].mean()), 2) if n else None})
            out[key] = {"label": label, "pearson": p, "spearman": s, "strength": strength_label(p["r"]),
                        "buckets": buckets, "synthetic": col in synthetic,
                        "observations_excluded": int(len(df) - p["n"])}
        limitations = [
            "Correlação não implica causalidade.",
            "Apenas avaliações com pedido e datas de entrega válidas são consideradas (ver 'observations_excluded').",
            "Pedidos com múltiplas entregas usam a entrega primária (primeiro envio).",
            "Valor-p por aproximação normal (adequado para amostras grandes).",
        ]
        return {"correlations": out, "limitations": limitations,
                "meta": self._meta({"buckets_nps_note": "NPS por faixa calculado com a mesma fórmula oficial (METRIC_NPS_001)"})}

    def comments(self, filters: Optional[dict] = None, top: int = 20) -> dict:
        f = self.clean_filters(filters)
        df = self.frame(f)
        total = int(len(df))
        with_comment = df[df["has_comment"].astype(bool)]
        res = {
            "evaluations_in_scope": total,
            "comments_available": int(len(with_comment)),
            "all": frequencies(with_comment["comment"], top),
            "promoters": frequencies(with_comment.loc[with_comment["score_category"] == "promoter", "comment"], top),
            "neutrals": frequencies(with_comment.loc[with_comment["score_category"] == "neutral", "comment"], top),
            "detractors": frequencies(with_comment.loc[with_comment["score_category"] == "detractor", "comment"], top),
            "injection_suspected": int(with_comment["injection_suspected"].astype(bool).sum()),
        }
        prom_t = {t["theme"]: t for t in res["promoters"]["themes"]}
        det_t = {t["theme"]: t for t in res["detractors"]["themes"]}
        comparison = []
        for theme in sorted(set(prom_t) | set(det_t)):
            p, d = prom_t.get(theme), det_t.get(theme)
            comparison.append({"theme": theme, "label": (p or d)["label"], "polarity": (p or d)["polarity"],
                               "promoter_count": p["count"] if p else 0, "detractor_count": d["count"] if d else 0,
                               "promoter_share": p["share"] if p else 0, "detractor_share": d["share"] if d else 0})
        res["theme_comparison"] = comparison
        res["meta"] = self._meta({"nlp": "Determinístico (sem LLM): normalização, stopwords PT, uni/bigramas, temas v1.0",
                                  "security": "Comentários são tratados como dados; suspeitas de prompt injection são "
                                              "apenas sinalizadas."})
        return res

    def filter_options(self) -> dict:
        df = self.frame({})
        opts = {d: sorted(v for v in df[d].dropna().unique().tolist()) for d in FILTER_DIMS}
        return {"options": opts, "date_range": {"min": to_jsonable(df["evaluation_date"].min()),
                                                "max": to_jsonable(df["evaluation_date"].max())}}
