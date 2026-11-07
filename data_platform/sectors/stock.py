"""Setor "Estoque · Pedidos travados" (Desafio 2 do case) — receita pronta, ligável/desligável em Configurações › Recursos.

Regras (requisitos RF2.1–RF2.3 do case):
  * item com estoque = 0                          → "Estoque zero" (pedido travado);
  * estoque > 0 mas menor que a demanda em aberto → FIFO por data do pedido: os mais antigos são atendidos, os
    excedentes ficam "Estoque insuficiente" (travados);
  * produto ausente do catálogo de estoque        → "Fora do catálogo" (NÃO é falta de estoque; não trava).
Dados pessoais da Base de Clientes (nome, telefone, e-mail) NÃO são ingeridos: o contato com o cliente é uma ação
proposta para aprovação humana, executada em modo simulado.
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from goops_core.db import Database
from goops_core.permissions import SYSTEM_PRINCIPAL
from goops_core.util import jdump, new_id, now_iso

from ..catalog import record_transformation, register_dataset
from ..lineage.registry import add_edge
from ..silver.mappings import product_line_from_name
from ..silver.transforms import _parse_dt
from ..storage import Lakehouse

DOMAIN = "estoque"
SOURCES = {
    "estoque_clientes_pedidos": ("Gocase · Base de Clientes (só pedido e data)", "seed/gocase/estoque/clientes.xlsx",
                                 ["Nome do Cliente", "Telefone", "E-mail"]),
    "estoque_detalhes_pedidos": ("Gocase · Detalhes dos pedidos", "seed/gocase/estoque/detalhes_pedidos.xlsx", []),
    "estoque_relatorio": ("Gocase · Relatório de estoque", "seed/gocase/estoque/estoque.xlsx", []),
}
GOLD_ITEMS = "gold_estoque_pedidos"
GOLD_PRODUCTS = "gold_estoque_produtos"
DIMS = ["month", "situacao", "linha_produto", "produto"]
OWNER = "Responsável Estoque"
MESSAGE = ("Olá! Seu pedido {pedido} está aguardando reposição do item {produto}. Você pode: (A) aguardar a reposição, "
           "(B) trocar por outro produto ou (C) cancelar com reembolso. Responda com A, B ou C.")


def _m(key, name, desc, ftext, fdef, unit, filters=None):
    return {"metric_key": key, "name": name, "description": desc, "formula_text": ftext,
            "formula_definition": {**fdef, "time_field": "data_pedido"}, "unit": unit, "dimensions": DIMS,
            "source_datasets": [GOLD_ITEMS], "filters": filters or [], "owner": OWNER, "domain": DOMAIN}


METRICS = [
    _m("ESTQ_ITENS_TRAVADOS", "Itens de pedido travados", "Itens de pedido sem estoque para atendimento (zero ou "
       "insuficiente após FIFO). Produtos fora do catálogo não contam.", "contagem(itens travados)", {"type": "count"},
       "itens", [{"field": "travado", "op": "is_true"}]),
    _m("ESTQ_PEDIDOS_TRAVADOS", "Pedidos travados", "Pedidos distintos com pelo menos um item travado.",
       "contagem distinta(pedido) onde travado", {"type": "count_distinct", "field": "pedido"}, "pedidos",
       [{"field": "travado", "op": "is_true"}]),
    _m("ESTQ_TAXA_TRAVADOS", "% de itens travados", "Itens travados / itens com produto no catálogo × 100.",
       "travado / no catálogo × 100",
       {"type": "rate", "numerator": {"field": "travado", "op": "is_true"}, "base_filter": {"field": "no_catalogo", "op": "is_true"}}, "%"),
    _m("ESTQ_PRODUTOS_ZERADOS", "Produtos zerados com demanda", "Produtos distintos com estoque zero e pedidos em aberto.",
       "contagem distinta(produto) onde situação = Estoque zero", {"type": "count_distinct", "field": "produto"}, "produtos",
       [{"field": "situacao", "op": "eq", "value": "Estoque zero"}]),
]
WIDGETS = [
    {"id": "e1", "title": "Pedidos travados", "metric_key": "ESTQ_PEDIDOS_TRAVADOS", "chart": "kpi", "group_by": None},
    {"id": "e2", "title": "Itens travados", "metric_key": "ESTQ_ITENS_TRAVADOS", "chart": "kpi", "group_by": None},
    {"id": "e3", "title": "% de itens travados", "metric_key": "ESTQ_TAXA_TRAVADOS", "chart": "kpi", "group_by": None},
    {"id": "e4", "title": "Produtos zerados com demanda", "metric_key": "ESTQ_PRODUTOS_ZERADOS", "chart": "kpi", "group_by": None},
    {"id": "e5", "title": "Itens travados por linha de produto", "metric_key": "ESTQ_ITENS_TRAVADOS", "chart": "bar", "group_by": "linha_produto"},
    {"id": "e6", "title": "Pedidos travados por mês", "metric_key": "ESTQ_PEDIDOS_TRAVADOS", "chart": "bar", "group_by": "month"},
    {"id": "e7", "title": "Itens travados por produto", "metric_key": "ESTQ_ITENS_TRAVADOS", "chart": "table", "group_by": "produto"},
]
AGENTS = [
    ("estq_avisar_clientes", "Avisar clientes de pedidos travados", "action_task",
     {"metric_key": "ESTQ_PEDIDOS_TRAVADOS", "rule": "above", "threshold": 0, "segment_by": None, "min_n": 1,
      "severity": "high", "category": "inventory", "action_type": "sector_customer_contact",
      "action_note": "Contato com os clientes dos pedidos travados oferecendo: (A) aguardar, (B) trocar ou (C) cancelar."},
     1440),
    ("estq_resumo", "Resumo de estoque", "summary",
     {"metric_keys": ["ESTQ_PEDIDOS_TRAVADOS", "ESTQ_ITENS_TRAVADOS", "ESTQ_PRODUTOS_ZERADOS"], "use_ai": False}, 10080),
]


def available() -> bool:
    from ..connectors.file_connector import import_dir
    return all((import_dir() / path).exists() for _, path, _ in SOURCES.values())


def seed_stock_sector(db: Database) -> bool:
    if not available():
        return False
    from ..ingestion.service import create_source
    from ..semantic.registry import _insert_metric
    ts = now_iso()
    created = False
    if not db.fetchone("SELECT key FROM domains WHERE key = ?", (DOMAIN,)):
        db.execute("INSERT INTO domains (key, name, description, owner, status, created_at) VALUES (?, ?, ?, ?, 'active', ?)",
                   (DOMAIN, "Estoque · Pedidos travados", "Cruzamento de estoque × pedidos (FIFO) e contato com clientes "
                    "dos pedidos travados — Desafio 2 do case.", OWNER, ts))
        created = True
    for key, (name, path, exclude) in SOURCES.items():
        if not db.fetchone("SELECT id FROM sources WHERE key = ?", (key,)):
            create_source(db, SYSTEM_PRINCIPAL, key=key, name=name, entity="custom", connector="file",
                          config={"path": path, "format": "xlsx", "seed": True, "domain": DOMAIN, "recipe": "stock",
                                  "exclude_fields": exclude, "schema_version": "estoque-xlsx-1"}, is_demo=False)
            created = True
    for m in METRICS:
        if not db.fetchone("SELECT id FROM semantic_metrics WHERE metric_key = ?", (m["metric_key"],)):
            _insert_metric(db, m, "domain", "active", SYSTEM_PRINCIPAL)
            created = True
    if not db.fetchone("SELECT id FROM dashboards WHERE key = ?", (DOMAIN,)):
        db.execute("INSERT INTO dashboards (id, key, domain, name, widgets, created_by, created_at, updated_at) "
                   "VALUES (?, ?, ?, ?, ?, 'system', ?, ?)", (new_id("DSH"), DOMAIN, DOMAIN, "Painel de estoque", jdump(WIDGETS), ts, ts))
        created = True
    for key, name, template, cfg, interval in AGENTS:
        if not db.fetchone("SELECT id FROM custom_agents WHERE key = ?", (key,)):
            db.execute("INSERT INTO custom_agents (id, key, domain, name, template, config, interval_minutes, enabled, "
                       "created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, 'system', ?, ?)",
                       (new_id("CAG"), key, DOMAIN, name, template, jdump(cfg), interval, ts, ts))
            created = True
    return created


def set_enabled(db: Database, enabled: bool) -> None:
    """Liga/desliga o setor inteiro: domínio, fontes e agentes (dados e histórico são preservados)."""
    if not db.fetchone("SELECT key FROM domains WHERE key = ?", (DOMAIN,)):
        if not enabled or not seed_stock_sector(db):
            return
    db.execute("UPDATE domains SET status = ? WHERE key = ?", ("active" if enabled else "inactive", DOMAIN))
    for key in SOURCES:
        db.execute("UPDATE sources SET status = ? WHERE key = ?", ("active" if enabled else "inactive", key))
    db.execute("UPDATE custom_agents SET enabled = ? WHERE domain = ?", (int(enabled), DOMAIN))


def _latest(lake: Lakehouse, key: str) -> pd.DataFrame:
    envs = lake.read_bronze(key)
    if not envs:
        return pd.DataFrame()
    last_run = envs[-1]["_run_id"]
    return pd.DataFrame([e["payload"] for e in envs if e["_run_id"] == last_run])


def compute_stuck(clientes: pd.DataFrame, detalhes: pd.DataFrame, estoque: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    orders = clientes.rename(columns={"Código do Pedido": "pedido", "Data do Pedido": "data_pedido"})[["pedido", "data_pedido"]]
    orders["pedido"] = orders["pedido"].astype(str).str.strip()
    orders["data_pedido"] = orders["data_pedido"].map(lambda v: _parse_dt(v)[0])
    orders = orders.dropna(subset=["pedido"]).drop_duplicates("pedido")
    items = detalhes.rename(columns={"Pedido": "pedido", "Detalhe do pedido": "produto"})[["pedido", "produto"]].copy()
    items["pedido"] = items["pedido"].astype(str).str.strip()
    items["produto"] = items["produto"].astype(str).str.strip()
    items = items.drop_duplicates()                       # linhas idênticas na planilha contam uma vez
    stock = estoque.rename(columns={"Produtos": "produto", "Estoque": "estoque"})[["produto", "estoque"]].copy()
    stock["produto"] = stock["produto"].astype(str).str.strip()
    stock["estoque"] = pd.to_numeric(stock["estoque"], errors="coerce")
    stock = stock.drop_duplicates("produto", keep="last")
    df = items.merge(orders, on="pedido", how="left").merge(stock, on="produto", how="left")
    df["no_catalogo"] = df["estoque"].notna()
    df["data_pedido"] = pd.to_datetime(df["data_pedido"])
    df = df.sort_values(["produto", "data_pedido", "pedido"], na_position="last", kind="stable")
    df["posicao_fila"] = df.groupby("produto").cumcount() + 1          # FIFO: mais antigo primeiro
    df["situacao"] = np.select(
        [~df["no_catalogo"], df["estoque"] <= 0, df["posicao_fila"] > df["estoque"]],
        ["Fora do catálogo", "Estoque zero", "Estoque insuficiente"], default="Atendível")
    df["travado"] = df["situacao"].isin(["Estoque zero", "Estoque insuficiente"])
    df["linha_produto"] = df["produto"].map(product_line_from_name)
    df["month"] = df["data_pedido"].dt.strftime("%Y-%m")
    df["_is_demo"] = False
    demand = df[df["no_catalogo"]].groupby("produto").agg(demanda=("pedido", "count"), travados=("travado", "sum"))
    prods = stock.set_index("produto").join(demand, how="left").fillna({"demanda": 0, "travados": 0}).reset_index()
    prods["demanda"] = prods["demanda"].astype(int)
    prods["travados"] = prods["travados"].astype(int)
    prods["deficit"] = (prods["demanda"] - prods["estoque"]).clip(lower=0).astype(int)
    prods["situacao"] = np.select([prods["estoque"] <= 0, prods["deficit"] > 0], ["Estoque zero", "Estoque insuficiente"], "OK")
    prods["linha_produto"] = prods["produto"].map(product_line_from_name)
    prods["_is_demo"] = False
    return {"items": df.reset_index(drop=True), "products": prods}


def build_stock(db: Database, lake: Lakehouse, pipeline_run_id: str, actor: str = "pipeline") -> Dict[str, Any]:
    active = {r["key"] for r in db.fetchall("SELECT key FROM sources WHERE status = 'active'")}
    if not set(SOURCES) <= active:
        return {"skipped": "setor Estoque desligado ou fontes inativas"}
    frames = {k: _latest(lake, k) for k in SOURCES}
    if any(f.empty for f in frames.values()):
        return {"skipped": "fontes ainda não sincronizadas"}
    out = compute_stuck(frames["estoque_clientes_pedidos"], frames["estoque_detalhes_pedidos"], frames["estoque_relatorio"])
    rows = {}
    for key, df, name, grain in ((GOLD_ITEMS, out["items"], "Itens de pedido × estoque (FIFO)", "1 linha por item de pedido"),
                                 (GOLD_PRODUCTS, out["products"], "Produtos × demanda", "1 linha por produto do catálogo")):
        w = lake.write_table(f"gold/domains/{DOMAIN}", key, df)
        register_dataset(db, key=key, layer="gold_domain", scope="domain", domain=DOMAIN, name=name,
                         description=f"Gold de domínio (estoque) · {name}. Receita FIFO do Desafio 2; sem dados pessoais.",
                         grain=grain, path=w["path"], fmt=w["format"], row_count=w["rows"], schema=w["schema"],
                         schema_version="estoque-1.0", is_demo=False, pipeline_run_id=pipeline_run_id)
        for s in SOURCES:
            add_edge(db, f"bronze:{s}", f"dataset:{key}", "receita estoque × pedidos (FIFO)")
        record_transformation(db, dataset_key=key, inputs=[f"bronze_{s}" for s in SOURCES], transform="stock FIFO recipe",
                              rule_version="1.0", rows_in=sum(len(f) for f in frames.values()), rows_out=w["rows"],
                              actor=actor, pipeline_run_id=pipeline_run_id)
        rows[key] = w["rows"]
    rows["travados"] = int(out["items"]["travado"].sum())
    return rows


def contact_reach(lake: Lakehouse, segment: str = "total") -> Dict[str, Any]:
    """Alcance de um contato com clientes de pedidos travados (contagens, sem dados pessoais)."""
    df = lake.read_table(f"gold/domains/{DOMAIN}", GOLD_ITEMS)
    t = df[df["travado"].astype(str).isin(["True", "true", "1"]) | (df["travado"] == True)]  # noqa: E712
    if segment not in ("total", "None", "", None) and segment in set(t["linha_produto"].astype(str)):
        t = t[t["linha_produto"].astype(str) == segment]
    sample = t.head(1)
    msg = MESSAGE.format(pedido=sample["pedido"].iloc[0], produto=sample["produto"].iloc[0]) if len(sample) else None
    return {"orders": int(t["pedido"].nunique()), "items": int(len(t)),
            "by_reason": t["situacao"].value_counts().to_dict(), "message_preview": msg}
