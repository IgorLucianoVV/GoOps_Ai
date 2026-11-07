# Camada semântica

## Corporate Semantic Registry (oficial)
| Chave | Métrica | Fonte |
|---|---|---|
| `METRIC_NPS_001` v1.0 | NPS = ((Promotores − Detratores) / Avaliações válidas) × 100; Promotor 9–10, Neutro 7–8, Detrator 0–6; sem avaliações válidas ⇒ **nulo** | gold_nps_analytics |
| `METRIC_PROMOTER_RATE_001` / `METRIC_DETRACTOR_RATE_001` | % promotores / detratores | gold_nps_analytics |
| `METRIC_AVG_SCORE_001` | Nota média | gold_nps_analytics |
| `METRIC_EVALUATIONS_001` | Total de avaliações válidas | gold_nps_analytics |
| `METRIC_LATE_DELIVERY_RATE_001` | % entregas concluídas após a previsão (sem tolerância) | gold_delivery_performance |
| `METRIC_DELIVERY_LEAD_TIME_001` | Prazo médio envio→entrega | gold_delivery_performance |

## Domain Semantic Registry
| Chave | Domínio | Relação |
|---|---|---|
| `CX_NPS_COMMENTED_001` | CX | NPS só de avaliações com comentário — **não equivalente** a METRIC_NPS_001 |
| `LOG_ON_TIME_TOLERANCE_001` | Logística | No prazo com tolerância de 1 dia — **não equivalente** a METRIC_LATE_DELIVERY_RATE_001 |
| `PRD_COMPLAINT_RATE_001` | Produtos | % avaliações com tema negativo |

## Regras
- Fórmulas são **definições declarativas** (`type: nps|rate|mean|count`, operadores permitidos) executadas por funções controladas — nunca código/SQL arbitrário.
- `equivalent_to` só é aceito se definição, filtros e fonte forem idênticos à métrica corporativa.
- Prefixo `METRIC_` reservado ao catálogo corporativo.
- Toda alteração cria versão `pending` (minor para documentação; **major** para fórmula/filtros), só vigora após aprovação; quem propõe não aprova; histórico preservado em `semantic_metric_versions`.
- Corporate: escrita/aprovação por Data Owner/Admin. Domínio: Domain Owner do domínio.
- Toda resposta analítica inclui `metric_key`, `version`, `scope` e `relationship`.
