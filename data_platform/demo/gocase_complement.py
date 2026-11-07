"""Complemento SINTÉTICO da seed Gocase — preenche lacunas das planilhas do case para a demo.

As planilhas reais não trazem datas de envio, previsão e entrega (só "Dias de entrega") nem pedidos ainda em
trânsito. Sem isso, taxa de atraso, prazo pedido→entrega, entregas no prazo e risco de atraso ficariam vazios.

O que é gerado (determinístico por seed, coerente com os dados reais):
  * kind="delivery_dates"   — para cada entrega REAL: data_envio, previsao_entrega e data_entrega.
      - data_pedido real (Base Pedidos) + dias de produção sintéticos  → data_envio
      - data_envio + "Dias de entrega" REAL (prazo de transporte)       → data_entrega
      - data_envio + SLA prometido sintético (tipo de frete × região)   → previsao_entrega
      Respeita a data real da avaliação NPS (a entrega acontece antes da pesquisa sempre que possível).
      Esses campos só preenchem lacunas (nunca sobrescrevem dados reais) e ficam marcados como sintéticos
      na Silver/Gold (`_synthetic_fields`, `datasets.synthetic_fields`).
  * kind="transit_orders" / "transit_deliveries" — pedidos e entregas FICTÍCIOS em trânsito, posteriores ao
      último pedido real (ids "DEMO-…", `is_demo`), para demonstrar risco de atraso de entregas em aberto.

Premissas (editáveis aqui e documentadas no README da seed):
  * "Dias de entrega" = prazo de transporte (envio→entrega). Indício: a pesquisa NPS chega em mediana 15 dias após
    o pedido, enquanto a mediana de "Dias de entrega" é 3 dias.
  * Origem dos envios: Fortaleza/CE (sede da Gocase). SLA prometido por tipo de frete + adicional por região.
NENHUM destes valores deve ser apresentado como dado real da Gocase.
"""
from __future__ import annotations

import zlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

SLA_DAYS = {"Expresso": 9, "Econômico": 12, "Grátis": 13}
SLA_DEFAULT = 12
REGION_OF_UF = {
    **{uf: "NE" for uf in ("CE", "RN", "PB", "PE", "AL", "SE", "BA", "PI", "MA")},
    **{uf: "N" for uf in ("PA", "AM", "AP", "RR", "RO", "AC", "TO")},
    **{uf: "CO" for uf in ("DF", "GO", "MT", "MS")},
    **{uf: "SE" for uf in ("SP", "RJ", "MG", "ES")},
    **{uf: "S" for uf in ("PR", "SC", "RS")},
}
REGION_EXTRA = {"NE": 0, "N": 2, "CO": 1, "SE": 1, "S": 2}
PRODUCTION_DAYS = {"Expresso": (1, 2), "default": (2, 4)}
TRANSIT_ORDERS = 120

_CACHE: Dict[tuple, Dict[str, List[dict]]] = {}


def _rng(key: str, seed: int) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32(f"{seed}:{key}".encode()))


def _fmt(ts) -> Optional[str]:
    return None if ts is None or pd.isna(ts) else pd.Timestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _uf(state) -> Optional[str]:
    from ..silver.transforms import _to_uf
    try:
        return _to_uf(state) if state is not None and not pd.isna(state) else None
    except Exception:  # noqa: BLE001
        return None


def sla_days(shipping_type: Optional[str], uf: Optional[str]) -> int:
    return SLA_DAYS.get(shipping_type or "", SLA_DEFAULT) + REGION_EXTRA.get(REGION_OF_UF.get(uf or "", ""), 1)


def _load_real(base) -> Dict[str, pd.DataFrame]:
    from ..silver.transforms import _parse_dt
    orders = pd.read_excel(base / "seed/gocase/pedidos.xlsx", dtype=object)
    deliveries = pd.read_excel(base / "seed/gocase/entregas.xlsx", dtype=object)
    nps = pd.read_excel(base / "seed/gocase/nps.xlsx", dtype=object, usecols=["Order ID", "Datecreated"])
    orders["order_date"] = orders["order_creation_date"].map(lambda v: _parse_dt(v)[0])
    nps["eval_date"] = nps["Datecreated"].map(lambda v: _parse_dt(v)[0])
    return {"orders": orders, "deliveries": deliveries, "nps": nps}


def generate_complement(seed: int = 42) -> Dict[str, List[dict]]:
    key = ("gocase_complement", seed)
    if key in _CACHE:
        return _CACHE[key]
    from ..connectors.file_connector import import_dir
    from ..silver.mappings import product_line_from_name
    real = _load_real(import_dir())
    o, d, n = real["orders"], real["deliveries"], real["nps"]
    first_order = o.groupby("reference")["order_date"].min()
    first_eval = n.groupby("Order ID")["eval_date"].min()

    dates: List[dict] = []
    for _, r in d.iterrows():
        ref = str(r["Código do Pedido"]).strip()
        rng = _rng(ref, seed)
        ship_type = r.get("tipo_frete")
        transit = pd.to_numeric(r.get("Dias de entrega"), errors="coerce")
        if pd.isna(transit):
            continue
        transit = int(transit)
        lo, hi = PRODUCTION_DAYS.get(ship_type, PRODUCTION_DAYS["default"])
        prod = int(rng.integers(lo, hi + 1))
        order_dt, eval_dt = first_order.get(ref), first_eval.get(ref)
        if order_dt is not None and pd.notna(order_dt):
            if eval_dt is not None and pd.notna(eval_dt):
                slack = (eval_dt - order_dt).days - transit - 1      # entrega antes da pesquisa, se possível
                prod = max(0, min(prod, slack))
            ship_dt = (order_dt + timedelta(days=prod)).normalize() + timedelta(hours=int(rng.integers(9, 18)),
                                                                                 minutes=int(rng.integers(0, 60)))
            if ship_dt < order_dt:
                ship_dt = order_dt + timedelta(hours=2)
        elif eval_dt is not None and pd.notna(eval_dt):            # entrega sem pedido na base: ancora na avaliação
            ship_dt = (eval_dt - timedelta(days=transit + int(rng.integers(1, 4)))).normalize() + timedelta(hours=10)
        else:
            continue
        actual_dt = ship_dt + timedelta(days=transit, hours=int(rng.integers(-3, 4)))
        est_dt = ship_dt.normalize() + timedelta(days=sla_days(ship_type, _uf(r.get("State"))), hours=23, minutes=59)
        dates.append({"delivery_id": ref, "reference": ref, "data_envio": _fmt(ship_dt),
                      "previsao_entrega": _fmt(est_dt), "data_entrega": _fmt(actual_dt),
                      "_complemento": "sintético: datas derivadas (produção e SLA simulados; transporte real)"})

    # ---- pedidos/entregas fictícios em trânsito (após o último pedido real) ----
    rng = np.random.default_rng(seed)
    last = pd.Timestamp(max(o["order_date"].max(), n["eval_date"].max()))
    recent = o[o["order_date"] >= o["order_date"].max() - timedelta(days=60)]
    recent = recent[pd.to_numeric(recent["Valor"], errors="coerce").fillna(0) > 0]
    carriers = d["delivery_service"].value_counts()
    carriers = carriers[carriers >= 200]
    ship_types = d["tipo_frete"].value_counts(normalize=True)
    states = d[["City", "State"]].dropna()
    t_orders, t_deliv = [], []
    for i in range(TRANSIT_ORDERS):
        oid = f"DEMO-{i + 1:04d}"
        item = recent.iloc[int(rng.integers(0, len(recent)))]
        ship_type = str(rng.choice(ship_types.index, p=ship_types.values))
        carrier = str(rng.choice(carriers.index, p=(carriers / carriers.sum()).values))
        loc = states.iloc[int(rng.integers(0, len(states)))]
        age = int(rng.choice([2, 4, 6, 8, 10, 13, 16, 19], p=[.16, .16, .16, .14, .12, .1, .09, .07]))
        order_dt = last - timedelta(days=age, hours=int(rng.integers(0, 12)))
        lo, hi = PRODUCTION_DAYS.get(ship_type, PRODUCTION_DAYS["default"])
        ship_dt = order_dt + timedelta(days=int(rng.integers(lo, hi + 1)))
        if ship_dt > last:
            ship_dt = last - timedelta(hours=6)
        est_dt = ship_dt.normalize() + timedelta(days=sla_days(ship_type, _uf(loc["State"])), hours=23, minutes=59)
        t_orders.append({"order_id": oid, "order_date": _fmt(order_dt), "product_id": item["material_name"],
                         "product_name": item["material_name"],
                         "product_line": product_line_from_name(item["material_name"]), "total": float(pd.to_numeric(item["Valor"], errors="coerce")),
                         "status": "em_transito", "_complemento": "sintético: pedido fictício em trânsito"})
        t_deliv.append({"delivery_id": f"{oid}-E1", "reference": oid, "transportadora": carrier, "tipo_frete": ship_type,
                        "data_envio": _fmt(ship_dt), "previsao_entrega": _fmt(est_dt), "data_entrega": None,
                        "status": "em_transito", "cidade": loc["City"], "uf": loc["State"],
                        "_complemento": "sintético: entrega fictícia em trânsito"})
    out = {"delivery_dates": dates, "transit_orders": t_orders, "transit_deliveries": t_deliv}
    _CACHE[key] = out
    return out
