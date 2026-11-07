# Data Lineage

Grafo em `lineage_edges` com nós `source:*`, `bronze:*`, `dataset:*`, `metric:*`, registrado automaticamente por ingestão, Silver, Gold e catálogo semântico.

Exemplo (`GET /api/data/lineage?node=metric:METRIC_NPS_001&direction=upstream`):
```
metric:METRIC_NPS_001 ← dataset:gold_nps_analytics ← dataset:silver_nps_evaluations ← bronze:demo_nps ← source:demo_nps
                                                  ← dataset:gold_orders ← silver_orders / gold_delivery_performance ← ...
```
Cada nó traz: camada, última execução de ingestão ou transformação (`transformations`: entradas, regra/versão, linhas, data, responsável), versão de schema, pipeline_run e flag de demo. Na interface, *Data Lineage* permite focar um nó, ver origem (upstream), impacto (downstream) ou ambos.
