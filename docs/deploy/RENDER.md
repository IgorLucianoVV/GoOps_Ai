# Publicar o GoOps AI no Render

Guia para colocar a plataforma no ar com link público e **acesso por login** (banca e time). O arquivo `render.yaml`
na raiz descreve tudo; o Render cria os recursos a partir dele.

## O que é criado

| Recurso | Tipo no Render | Público? | Plano sugerido | Custo aprox.* |
|---|---|---|---|---|
| `goops-web` (Next.js) | Web service (Docker) | **Sim** — é o link que você compartilha | `0.5c-512mb` | US$ 7/mês |
| `goops-api` (FastAPI + agentes) | Private service (Docker) | Não — só a rede interna do Render | `1c-2g` | US$ 25/mês |
| `goops-var` (Lakehouse, relatórios) | Disco persistente na API | — | 1 GB | US$ 0,25/mês |
| `goops-db` (PostgreSQL) | Render Postgres | Não (sem IP externo) | `0.1c-256mb` | US$ 6/mês |

\*Preços da página de preços do Render em nov/2026, cobrados proporcionalmente ao tempo ligado. Versão econômica:
API em `0.5c-512mb` (≈ US$ 20/mês no total) — funciona, mas fica no limite de memória ao rodar a validação ponta a
ponta. Depois do evento dá para suspender os serviços no painel.

Só o frontend fica exposto. O navegador fala com `goops-web` em `/api`, e o Next.js repassa para a API pela rede
privada — mesma origem, cookies de sessão `Secure` e CSRF funcionando como no ambiente local.

## Antes de começar

1. **Código no GitHub:** faça commit e push (inclui `render.yaml`, `.dockerignore` e `docs/deploy/`).
2. **Conta no Render** ligada ao GitHub com acesso ao repositório `IgorLucianoVV/GoOps_Ai`, e um cartão cadastrado
   (os planos acima são pagos; o plano gratuito não tem serviço privado nem disco).
3. **Uma senha forte** para os usuários de demonstração (16+ caracteres). Guarde num gerenciador de senhas.

## Passo a passo

1. No Render: **New › Blueprint** › escolha o repositório `GoOps_Ai`, branch `main`.
2. O Render lê o `render.yaml` e lista `goops-api`, `goops-web` e `goops-db`. Ele pede os valores marcados como
   secretos:
   - `DEMO_ADMIN_PASSWORD` — **obrigatório**: a senha forte acima. Vale para `admin@goops.local` e os demais
     usuários `*@goops.local` criados na primeira subida.
   - `AI_PROXY_API_KEY` e `TELEGRAM_BOT_TOKEN` — opcionais. Pode deixar em branco e salvar depois pela própria
     plataforma (Configurações), onde ficam cifrados no banco. Nunca coloque tokens no código.
3. **Apply.** O primeiro build leva alguns minutos (imagens Docker da API e do frontend).
4. Quando a API sobe, ela aplica as migrações e carrega os dados de demonstração **em segundo plano** (cerca de
   1–3 min no Postgres). Nesse intervalo as telas podem aparecer vazias; acompanhe em *goops-api › Logs* até a linha
   `Seed inicial concluída em segundo plano`.
5. Abra a URL do `goops-web` (algo como `https://goops-web.onrender.com`) e entre com `admin@goops.local` e a senha
   do passo 2.

## Depois de subir (configuração da demonstração)

- **IA:** *Configurações › Modelos e chaves* → **Usar AI Proxy Gogroup** e salve o token.
- **Telegram:** *Configurações › Canal do time* (token do bot e ID do grupo) e vincule sua conta em *Canal do time*.
- **Turno automático:** *Configurações › Monitor, agendador e retenção* → ligue o job do Agente de Atendimento.
- **Validação:** *Agentes de IA › Validação ponta a ponta* → **Rodar validação** (a etapa 13 do modo apresentação
  mostra esse relatório).
- **Modo apresentação:** botão **Apresentar** na barra superior.

## Acessos da banca e do time

Os usuários `*@goops.local` são conhecidos publicamente (estão no README), então a proteção é a senha forte.

1. Para cada pessoa, crie um usuário próprio em *Configurações › Usuários › Novo usuário*, com o papel adequado:
   **Leitor** para quem só vai navegar, **Atendente** para quem vai responder e aprovar ações do atendimento.
2. Envie a senha inicial por um canal privado (não em grupo aberto) e peça para trocar em *Minha conta*.
3. Usuários de demonstração que ninguém vai usar: desative ou troque a senha (*Nova senha*) em *Usuários*.

## Atualizações

Cada push na `main` dispara um novo deploy automático. A API tem disco, então o deploy dela derruba o serviço por
alguns segundos (o Render para a instância antiga antes de subir a nova). **Não faça push durante o pitch.**

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Tela de login diz que o backend não respondeu | O frontend foi construído antes de a API existir na rede privada | Em `goops-web`: *Manual Deploy › Clear build cache & deploy*. Se persistir, defina `API_INTERNAL_URL` como `http://<hostname-da-api>:8000` (hostname em *goops-api › Connect*) e faça o deploy de novo |
| Telas vazias logo após a primeira subida | Carga inicial ainda rodando | Aguarde a linha `Seed inicial concluída` nos logs da API |
| API reinicia sozinha (logs com *out of memory*) | Plano de 512 MB | Suba a API para `1c-2g` |
| Login recusado com a senha certa | `DEMO_ADMIN_PASSWORD` só vale na criação dos usuários | Troque a senha pelo painel de usuários com outra conta admin, ou recrie o banco |

## Segurança (o que já vem configurado)

- `APP_ENV=production`: exige `SECRET_KEY` (gerada pelo Render), cookies `Secure`, CORS restrito.
- API e banco sem acesso pela internet; só o frontend é público.
- Execução de ações **simulada**; ações em áreas críticas continuam exigindo aprovação humana.
- A API roda sem privilégios (usuário `goops`); o entrypoint só ajusta a posse do disco antes de trocar de usuário.
