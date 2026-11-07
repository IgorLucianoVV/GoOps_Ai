# Seed Gocase (dados do case)

Planilhas fornecidas no Business Case (Analista de Dados & Performance — Gocase), usadas como seed padrão:

| Arquivo | Origem | Grão | Chave de pedido |
|---|---|---|---|
| `nps.xlsx` | 1. Base de NPS | 1 avaliação | `Order ID` |
| `pedidos.xlsx` | 2. Base Pedidos | 1 item de pedido | `reference` |
| `entregas.xlsx` | 3. Base de entregas | 1 entrega | `Código do Pedido` |

Carregadas pelo conector `file` com o perfil de mapeamento `gocase_xlsx` (`data_platform/silver/mappings.py`).
Por minimização de dados pessoais, as colunas `Name` e `Ipaddress` do NPS **não** são ingeridas (nem na Bronze).
O identificador da avaliação é `Queuereviewemailid` (único por linha).
Limitações da fonte: não há datas de envio/previsão/entrega (apenas "Dias de entrega", interpretado como prazo de
transporte envio→entrega) nem pedidos em aberto. Essas lacunas são preenchidas por um **complemento SINTÉTICO**
(`data_platform/demo/gocase_complement.py`), sempre sinalizado na plataforma e desativável em Lakehouse › Fontes.
Premissas do complemento: produção 1–2 dias (Expresso) ou 2–4 dias (demais), SLA prometido Expresso 9 / Econômico 12 /
Grátis 13 dias + adicional regional (origem Fortaleza/CE), entrega antes da data real da pesquisa NPS sempre que possível.
