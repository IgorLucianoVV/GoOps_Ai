# Segurança

- **Autenticação**: senha PBKDF2-SHA256 (200k iterações); token assinado HMAC-SHA256 com expiração. No navegador, a sessão fica em **cookie httpOnly** (SameSite=Lax, Secure em produção) — o JavaScript nunca acessa o token. Requisições que alteram estado exigem **CSRF double-submit** (`X-CSRF-Token` = cookie `goops_csrf`). Clientes de API podem usar Bearer (`issue_token: true` no login). `SECRET_KEY` obrigatório em produção.
- **Chaves de API configuradas na interface**: cifradas em repouso (encrypt-then-MAC com chaves derivadas do SECRET_KEY, `goops_core/crypto.py`), nunca retornadas pela API (apenas sufixo), nunca registradas em logs/auditoria.
- **Usuários**: não é possível remover o último administrador nem desativar a si mesmo; redefinição de senha auditada.
- **Autorização**: RBAC (`goops_core/permissions.py`) + escopo por domínio + sensibilidade (`data:pii`). Corporate vs domain metrics com permissões distintas.
- **Agentes**: permissões mínimas por agente; nunca aprovam; executam apenas operações aprovadas por **usuário** humano; sem SQL arbitrário; ferramentas com allowlist de parâmetros.
- **Políticas**: ações em pagamentos, pedidos, estoque ou clientes exigem aprovação de Admin/Data Owner/Domain Owner do domínio da ação. Execução apenas `simulated`.
- **SQL injection**: 100% consultas parametrizadas; nomes de colunas/tabelas nunca vêm do usuário.
- **Prompt injection**: comentários/payloads tratados como dados; comentários com padrão de injeção são **excluídos** de qualquer prompt (não apenas sinalizados) e marcações de controle são removidas (`agents/routing/sanitize.py`); prompt de sistema com guardrail; saídas de LLM validadas contra contrato (ex.: lista fechada de temas) ou usadas só como narrativa — ações vêm do catálogo determinístico.
- **Segredos**: só via variáveis de ambiente; credenciais inline em configs de fontes são rejeitadas; logs e auditoria redigem segredos; a API de settings mostra apenas se uma chave está configurada.
- **Rate limit**: por IP; `RATE_LIMIT_BACKEND=memory` (uma instância) ou `database` (compartilhado entre instâncias). Headers `X-Content-Type-Options`, `X-Request-ID`.
- **Dados pessoais**: mascaramento por papel; demo usa IDs pseudônimos sintéticos.
- **Retenção**: configurável em Settings; Bronze só é expurgado quando todos os registros do arquivo existem em execuções posteriores (reprocessamento sem perda); quarentena e logs de LLM por idade; auditoria nunca é expurgada.
- **Ambientes**: `APP_ENV` (development/test/production); token efêmero em dev sem SECRET_KEY.
