# Modelo de dados

## Chave canônica
`order_id` (string, zeros à esquerda preservados): Pedidos `Order ID` · Avaliações `Código do Pedido` · Entregas `reference`.
Relacionamentos 1:N (pedido → avaliações, pedido → entregas). **Nunca** se assume 1:1.

## Perfis de mapeamento
| Perfil | Pedidos | Avaliações | Entregas | Observações |
|---|---|---|---|---|
| `default` | `Order ID` | `Código do Pedido` | `reference` | especificação / dados sintéticos |
| `gocase_xlsx` | `reference` (por **item**; chave `reference:order_id`) | `Order ID` (id `Queuereviewemailid`) | `Código do Pedido` | planilhas do case; sem datas de entrega (usa `Dias de entrega`); UF por nome do estado |

Perfis personalizados são criados em *Data Lakehouse › Mapeamentos* (versionados no banco). Ver README › "Configurar integrações reais e mudanças de API".

## Silver
| Dataset | Grão | Campos principais |
|---|---|---|
| `silver_orders` | 1 por pedido | order_id, reference, customer_id, order_date, product_id, product_name, product_line, order_status, order_total, state, n_evaluations, n_deliveries |
| `silver_nps_evaluations` | 1 por avaliação | evaluation_id, order_id, reference, score, comment, evaluation_date, customer_id, channel, is_orphan |
| `silver_order_items` | 1 por item | order_item_id, order_id, product_name, product_line, order_total (valor do item) — fontes por item |
| `silver_deliveries` | 1 por entrega | delivery_id, order_id, carrier, shipping_type, shipping_date, estimated_delivery_date, actual_delivery_date, delivery_status, is_orphan |
Todos carregam metadados `_source, _run_id, _bronze_id, _ingested_at, _payload_hash, _is_demo, _dq_flags`.

## Corporate Gold
| Dataset | Grão | Observação |
|---|---|---|
| `gold_delivery_performance` | entrega | is_late (sem tolerância), delay_days, lead times, ship_month |
| `gold_orders` | pedido | entregas agregadas por pedido **antes** de joins (entrega primária = primeiro envio) |
| `gold_nps_analytics` | avaliação | join N:1 com gold_orders validado (`validate="many_to_one"`), categoria, temas, flags |
| `gold_customer_experience` | cliente | agregados por cliente |
| `gold_product_performance` | produto | NPS, detratores, atraso |
| `gold_regional_performance` | UF | NPS, detratores, atraso, prazo |

## Domain Gold
`cx_comment_insights`, `cx_detractor_drivers`, `logistics_carrier_scorecard`, `logistics_delay_risk`, `products_complaint_frequency`.

## Metadados (PostgreSQL/SQLite)
Ver `infrastructure/database/migrations/0001_initial_schema.sql`: users, audit_log, domains, sources, ingestion_runs, ingestion_failures, pipeline_runs, datasets, transformations, lineage_edges, dq_rules, dq_results, quarantine, data_dictionary, semantic_metrics, semantic_metric_versions, incidents, incident_events, operations, workflow_runs, agent_runs, routing_decisions, llm_calls, app_settings.

> Os campos de origem são um **modelo inicial**, não um contrato confirmado. Ajustar após a documentação real das APIs.
