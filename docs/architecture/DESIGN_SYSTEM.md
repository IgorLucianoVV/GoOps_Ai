# Design System e princípios de UX — GoOps AI

## 1. Identidade visual (paleta inspirada na Gocase)

| Token | Hex | Uso | Fonte |
|---|---|---|---|
| `brand-600` | `#005BAA` | Botão primário, links, série principal dos gráficos | Brandfetch — "Endeavour" |
| `navy-900` | `#010C76` | Detalhe do símbolo do produto | Brandfetch — "Navy Blue" |
| `accent-400` | `#E9ED9A` | Símbolo, destaques na tela de login | Brandfetch — "Primrose" |
| `coral-400/500` | `#F37053` / `#E2583A` | Marcador de item ativo, rótulos de seção, série secundária | paleta pública anterior da Gocase (Brandfetch, via busca) |
| `peach-400` | `#FFC67E` | Forma decorativa no login | idem |

**Regra de uso (revisão "muito azul"):** superfícies são **neutras** (cinzas quentes no claro, carvão no escuro). A cor da
marca aparece com parcimônia — azul só para ação/links e dados; coral e primrose como acentos. Nada de grandes áreas azuis.

- A Gocase anunciou uma identidade **lúdica, colorida e com formas geométricas**. O GoOps AI traduz isso de forma sóbria
  para um produto B2B: superfícies neutras, azul para ação, acentos coral e primrose e formas geométricas simples na marca do produto
  e na tela de login.
- **Logotipos e demais elementos de identidade da Gocase/Gogroup NÃO são reproduzidos.** O site oficial da Gocase informa
  que a reprodução de elementos de identidade exige autorização expressa. A marca do produto é um símbolo geométrico
  original + o nome "GoOps AI". A paleta é **configurável por tokens** (`styles/globals.css`): para uso oficial, valide os
  valores com o time de Brand (brandbook) e substitua os tokens sem alterar componentes.

## 2. Tokens e temas
- Cores semânticas via variáveis CSS (`--c-*`) consumidas pelo Tailwind (`tailwind.config.ts`). Tema **claro** (padrão
  conforme o sistema) e **escuro** (carvão neutro), alternáveis na barra superior ou na paleta de comandos; preferência persistida
  e aplicada antes da pintura (sem "flash").
- Escalas: `ink` (superfícies e bordas), `slate` (texto), `brand`, `navy`, `accent` e estados (`emerald` sucesso, `rose`
  erro, `amber` atenção, `sky` informação, `violet`, `teal`).

### Contraste verificado (WCAG 2.2 AA — texto ≥ 4.5:1; elementos não textuais ≥ 3:1)
| Par | Claro | Escuro |
|---|---|---|
| Texto principal / card | 17.7:1 | 16.6:1 |
| Texto secundário (`slate-400`) / card | 7.7:1 | 6.8:1 |
| Texto auxiliar (`slate-500`) / fundo | 5.5:1 | 5.7:1 |
| Sucesso / Erro / Atenção (texto) | 5.4 / 6.5 / 5.9 | 9.8 / 7.7 / 11.0 |
| Coral (texto de rótulo `coral-300`) | 5.5:1 | 8.6:1 |
| Botão primário (texto branco sobre azul) | 6.8:1 | 5.4:1 |
| Links (azul) / card | 6.8:1 | 8.2:1 |
| Marcador ativo coral / superfície (não textual) | 3.4:1 | ≥ 3:1 |
O cálculo usa a fórmula de luminância relativa do WCAG (script reproduzível descrito no histórico do projeto).

## 3. Visualização de dados
- Paleta categórica segura para daltonismo (base **Okabe–Ito**); NPS em escala **divergente azul → laranja**
  (não depende de vermelho/verde). Promotores/neutros/detratores = azul/cinza/laranja, sempre com legenda textual.
- Todo gráfico é um `figure role="img"` com rótulo e **resumo textual** (ex.: "2025-04: 85,5; 2025-05: 89,9…");
  tabelas equivalentes ficam disponíveis em "Ver dados em tabela" (divulgação progressiva).
- Variações usam **ícone + sinal + texto** (▲/▼, "melhora"/"piora" para leitores de tela) — nunca só cor (WCAG 1.4.1).
- Números com `tabular-nums` e formatação pt-BR; nulos exibidos como "—" (nunca como zero).

## 4. Heurísticas de Nielsen aplicadas
| # | Heurística | Implementação |
|---|---|---|
| 1 | Visibilidade do estado do sistema | Toasts de sucesso/erro (aria-live), skeletons de carregamento, breadcrumb, selo de dados sintéticos, status de pipeline/agendador, "gerado por: determinístico/LLM" |
| 2 | Correspondência com o mundo real | Linguagem de negócio em pt-BR, rótulos como "Promotores (9–10)", unidades explícitas |
| 3 | Controle e liberdade | Diálogos de confirmação com "Cancelar" focado por padrão e Esc; filtros removíveis por chip; "Limpar filtros" |
| 4 | Consistência e padrões | Uma única arquitetura de informação (`components/nav.ts`) para menu, breadcrumb e busca; componentes e cores semânticas únicos |
| 5 | Prevenção de erros | Confirmação antes de ações destrutivas/críticas (aprovar/rejeitar ação, recarregar seed, retenção, desativar fonte, encerrar incidente); botões desabilitados quando inválidos; aprovação humana obrigatória para áreas críticas |
| 6 | Reconhecer em vez de lembrar | Menu com grupo ativo aberto, item ativo com marcador; tooltips (?) com a fórmula oficial ao lado dos KPIs; filtros ativos visíveis |
| 7 | Flexibilidade e eficiência | Paleta de comandos **Ctrl/⌘ + K** para páginas e ações; temas claro/escuro |
| 8 | Estética e minimalismo | Grupos do menu recolhíveis, tabelas de apoio sob "Ver dados", hierarquia KPI → gráfico → detalhe |
| 9 | Reconhecer, diagnosticar e recuperar erros | `ErrorBox` traduz o erro em causa + próximo passo + link (ex.: 409 → "Abrir Data Lakehouse"; 403 → como pedir acesso; rede → verificar API) |
| 10 | Ajuda e documentação | Ajuda contextual (?) nos indicadores, estados vazios que ensinam o que aparecerá ali e como popular |

## 5. Estados vazios (NN/g)
Todo estado vazio comunica **status**, **o que aparecerá** e oferece um **caminho direto** (ex.: Overview sem dados →
"Carregar seed Gocase"; sem incidentes → "Executar ciclo agora").

## 6. Acessibilidade (WCAG 2.2 AA)
Link "Pular para o conteúdo"; landmarks (`nav`, `main`, `header`, `search`); `aria-current` na navegação; foco visível
de 3 px; diálogos com `aria-modal`, foco preso e devolvido; tabelas com `scope`/`caption`; linhas
clicáveis acessíveis por teclado; alvos de toque ≥ 36 px; `prefers-reduced-motion` respeitado; mostrar/ocultar senha.

## Referências
- Nielsen Norman Group — 10 Usability Heuristics: https://www.nngroup.com/articles/ten-usability-heuristics/
- NN/g — Progressive Disclosure: https://www.nngroup.com/articles/progressive-disclosure/
- NN/g — Designing Empty States in Complex Applications: https://www.nngroup.com/articles/empty-state-interface-design/
- W3C — WCAG 2.2 (Contrast Minimum 1.4.3, Non-text Contrast 1.4.11, Focus Appearance 2.4.13): https://www.w3.org/WAI/WCAG22/Understanding/
- Brandfetch — Gocase brand colors: https://brandfetch.com/gocase.com.br
- Gocase — nova identidade visual (direção: cores diversas e lúdicas, formas geométricas): https://us.gocase.com/new-identity
