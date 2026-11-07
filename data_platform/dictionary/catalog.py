"""Data Dictionary: documentação de campos por dataset (curada + derivada do schema real)."""
from __future__ import annotations

from typing import Dict, List, Optional

from goops_core.db import Database
from goops_core.util import jdump, jload, new_id

# campo -> (nome de negócio, descrição, formato, validação, relacionamentos, sensibilidade)
FIELD_DOCS: Dict[str, tuple] = {
    "order_id": ("Código do pedido (chave canônica)", "Chave canônica de relacionamento. Origem: Pedidos 'Order ID', "
                 "Avaliações 'Código do Pedido', Entregas 'reference'.", "string (zeros à esquerda preservados)",
                 "obrigatório nas fontes que o exigem", "orders.order_id 1:N deliveries.order_id; 1:N evaluations.order_id",
                 "internal"),
    "reference": ("Referência original", "Identificador conforme recebido da fonte (preservado).", "string", None, None, "internal"),
    "evaluation_id": ("Avaliação", "Identificador da avaliação NPS.", "string", "obrigatório", None, "internal"),
    "delivery_id": ("Entrega", "Identificador da entrega.", "string", "obrigatório", "N:1 orders", "internal"),
    "customer_id": ("Cliente", "Identificador do cliente (dado pessoal pseudonimizado).", "string", None, None, "pii"),
    "score": ("Nota NPS", "Nota de 0 a 10 informada pelo cliente.", "inteiro", "0 <= nota <= 10; fora => quarentena",
              None, "internal"),
    "score_category": ("Categoria NPS", "Promotor (9-10), Neutro (7-8), Detrator (0-6).", "promoter|neutral|detractor",
                       None, None, "internal"),
    "comment": ("Comentário", "Texto livre do cliente. Tratado sempre como DADO (nunca como instrução).", "texto", None,
                None, "pii"),
    "evaluation_date": ("Data da avaliação", "Referência temporal do NPS.", "datetime", "data válida obrigatória", None, "internal"),
    "eval_month": ("Mês da avaliação", "Mês (AAAA-MM) da data da avaliação.", "AAAA-MM", None, None, "internal"),
    "order_date": ("Data do pedido", "Data de criação do pedido.", "datetime", "data válida obrigatória", None, "internal"),
    "order_total": ("Valor do pedido", "Valor total do pedido em BRL.", "decimal", ">= 0", None, "internal"),
    "state": ("UF", "Unidade federativa de entrega.", "UF (2 letras)", "UF válida", None, "internal"),
    "product_id": ("Produto", "Identificador do produto.", "string", None, None, "internal"),
    "product_line": ("Linha de produto", "Agrupamento de produtos.", "texto", None, None, "internal"),
    "carrier": ("Transportadora", "Transportadora responsável.", "texto", "identificável quando houver envio", None, "internal"),
    "shipping_type": ("Tipo de frete", "Modalidade de frete.", "texto", None, None, "internal"),
    "shipping_date": ("Data de envio", "Data de envio da entrega.", "datetime", None, None, "internal"),
    "estimated_delivery_date": ("Previsão de entrega", "Data prevista de entrega.", "datetime", None, None, "internal"),
    "actual_delivery_date": ("Data de entrega", "Data efetiva de entrega.", "datetime", ">= data de envio", None, "internal"),
    "is_late": ("Atrasada", "Entrega concluída após a data prevista (sem tolerância).", "booleano", None, None, "internal"),
    "delay_days": ("Dias de atraso", "Dias entre previsão e entrega (>= 0).", "decimal", None, None, "internal"),
    "lead_time_ship_to_delivery_days": ("Prazo envio→entrega", "Dias entre envio e entrega.", "decimal", None, None, "internal"),
    "lead_time_order_to_delivery_days": ("Prazo pedido→entrega", "Dias entre pedido e entrega.", "decimal", None, None, "internal"),
    "is_orphan": ("Órfão", "Registro sem pedido correspondente (mantido e sinalizado).", "booleano", None, None, "internal"),
    "themes": ("Temas", "Temas detectados no comentário (dicionário v1.0).", "lista separada por |", None, None, "internal"),
    "delivery_days": ("Dias de entrega (informado)", "Prazo informado pela fonte quando não há datas de entrega.", "inteiro", ">= 0", None, "internal"),
    "city": ("Cidade", "Cidade de entrega.", "texto", None, None, "internal"),
    "n_items": ("Itens no pedido", "Quantidade de itens agregados no pedido.", "inteiro", None, None, "internal"),
    "product_lines": ("Linhas no pedido", "Linhas de produto presentes no pedido.", "lista |", None, None, "internal"),
    "late_evaluable": ("Atraso avaliável", "Há data prevista e efetiva para medir atraso.", "booleano", None, None, "internal"),
    "lead_time_source": ("Origem do prazo", "Origem do prazo envio→entrega: 'dias_informados' (\"Dias de entrega\" da fonte) ou 'datas' (calculado).", "texto", None, None, "internal"),
    "order_item_id": ("Item do pedido", "Chave do item (reference:order_id na planilha Gocase).", "string", None, "N:1 orders", "internal"),
    "external_order_number": ("Nº interno do pedido", "Identificador numérico interno da fonte.", "string", None, None, "internal"),
    "_is_demo": ("Dado de demonstração", "Indica dados sintéticos de demonstração.", "booleano", None, None, "internal"),
    "_synthetic_fields": ("Campos sintéticos", "Campos deste registro preenchidos pelo complemento SINTÉTICO de demonstração "
                          "(não são dados reais).", "lista |", None, None, "internal"),
    "_dq_flags": ("Alertas de qualidade", "Regras de qualidade (warning) violadas pelo registro.", "lista |", None, None, "internal"),
}


def sync_dictionary(db: Database) -> int:
    count = 0
    datasets = db.fetchall("SELECT key, schema_def, layer FROM datasets WHERE layer <> 'bronze'")
    with db.connect() as c:
        for ds in datasets:
            schema = jload(ds["schema_def"], {})
            origin_row = c.fetchone("SELECT inputs FROM transformations WHERE dataset_key = ? ORDER BY executed_at DESC "
                                    "LIMIT 1", (ds["key"],))
            origin = ", ".join(jload(origin_row["inputs"], [])) if origin_row else None
            for field, dtype in schema.items():
                doc = FIELD_DOCS.get(field)
                business, desc, fmt, validation, rel, sens = doc if doc else (
                    field.replace("_", " ").capitalize(), None, None, None, None, "internal")
                c.execute(
                    "INSERT INTO data_dictionary (id, dataset_key, field, business_name, description, data_type, origin, "
                    "format, required, validation, relationships, sensitivity) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT (dataset_key, field) DO UPDATE SET business_name = excluded.business_name, "
                    "description = excluded.description, data_type = excluded.data_type, origin = excluded.origin, "
                    "format = excluded.format, required = excluded.required, validation = excluded.validation, "
                    "relationships = excluded.relationships, sensitivity = excluded.sensitivity",
                    (new_id("DD"), ds["key"], field, business, desc, dtype, origin, fmt,
                     int(bool(validation and "obrigat" in validation)), validation, rel, sens))
                count += 1
    return count


def list_dictionary(db: Database, dataset_key: Optional[str] = None, q: Optional[str] = None) -> List[dict]:
    clauses, params = [], []
    if dataset_key:
        clauses.append("dataset_key = ?"); params.append(dataset_key)
    if q:
        clauses.append("(LOWER(field) LIKE ? OR LOWER(business_name) LIKE ?)")
        params.extend([f"%{q.lower()}%", f"%{q.lower()}%"])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.fetchall(f"SELECT * FROM data_dictionary {where} ORDER BY dataset_key, field", params)
    for r in rows:
        r["required"] = bool(r["required"])
    return rows
