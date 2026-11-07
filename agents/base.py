"""Infraestrutura comum dos agentes: contexto, registro de execuções e catálogo."""
from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from goops_core.db import Database
from goops_core.errors import GoOpsError
from goops_core.incidents import add_event, register_agent
from goops_core.permissions import Principal, agent_principal
from goops_core.util import jdump, jload, new_id, now_iso
from data_platform.storage import Lakehouse

from .instructions import SLOTS, _draft
from .routing.router import CostRouter

AGENT_CATALOG: Dict[str, Dict[str, Any]] = {
    "supervisor": {"name": "Supervisor GoOps", "role": "Coordena agentes, prioriza incidentes, controla o fluxo e "
                   "solicita aprovação humana.", "level": "orquestração (determinístico)"},
    "monitor": {"name": "Agente Monitor", "role": "Monitora indicadores governados, detecta anomalias e cria incidentes.",
                "level": "nível 0 (regras e estatística)"},
    "investigation": {"name": "Agente de Investigação", "role": "Investiga incidentes cruzando domínios, qualidade e "
                      "linhagem; apresenta hipóteses com confiança e evidências.",
                      "level": "nível 0 + narrativa opcional nível 3"},
    "resolution": {"name": "Agente de Resolução", "role": "Elabora plano de resolução a partir do catálogo de ações, "
                   "estima impacto e risco, solicita aprovação e executa apenas ações autorizadas (simulado).",
                   "level": "nível 0 + narrativa opcional nível 3"},
    "assistant": {"name": "Pergunte ao GoOps", "role": "Responde perguntas em linguagem natural usando apenas métricas "
                  "oficiais via ferramentas governadas, com as permissões de quem pergunta e citações.",
                  "level": "nível 3/2 com ferramentas (contingência determinística)"},
    "support": {"name": "Agente de Atendimento", "role": "Tria contatos de WhatsApp, e-mail e Reclame Aqui: intenção, "
                "pedido, veracidade da reclamação, urgência e matriz automático × humano; responde assuntos informativos "
                "e propõe ações (chamado, troca, reenvio) que seguem a política de aprovação.",
                "level": "nível 0 (regras explicáveis) + resposta opcional nível 2"},
    "validation": {"name": "Agente de Validação", "role": "Valida dados usados, políticas e resultados; avalia se o "
                   "problema foi resolvido.", "level": "nível 0"},
}


# "O que cada agente faz" — exibido na tela Agentes de IA. Texto descritivo; a lógica continua no código de cada agente.
AGENT_PROFILES: Dict[str, Dict[str, List[str]]] = {
    "supervisor": {
        "does": ["Executa o ciclo de monitoramento e prioriza incidentes por severidade.",
                 "Conduz o fluxo do incidente: validação → investigação → plano → aprovação humana → execução → validação.",
                 "Retoma o fluxo quando uma pessoa aprova ou rejeita uma ação.",
                 "Escreve o resumo executivo do incidente ao final (IA opcional)."],
        "triggers": ["Botão “Ciclo completo” nesta tela", "Agendador (job de monitoramento)", "Decisão humana numa ação"],
        "guardrails": ["Não aprova nem executa ações por conta própria.", "Não conversa livremente com outros agentes: o fluxo é um grafo com estado persistido."],
    },
    "monitor": {
        "does": ["Observa métricas governadas: queda de NPS (mês a mês ou vs. média de 3 meses), aumento de atraso por "
                 "transportadora e concentração de detratores por linha.",
                 "Abre incidente quando um limiar é ultrapassado, sem duplicar (fingerprint)."],
        "triggers": ["Ciclo de monitoramento (botão ou agendador)"],
        "guardrails": ["100% regras e estatística — não usa IA.", "Limiares editáveis em Configurações › Monitor."],
    },
    "investigation": {
        "does": ["Decompõe a variação da métrica por dimensão em efeito desempenho × composição, com teste z.",
                 "Corrobora com atraso/prazo, temas de comentários, qualidade de dados e linhagem.",
                 "Gera hipóteses com confiança, evidências e limitações; escreve a narrativa (IA opcional).",
                 "Classifica comentários de detratores sem tema numa lista fechada (modelo pequeno, opcional)."],
        "triggers": ["Incidente aberto pelo Monitor (com investigação automática)", "Botão “Investigar” no incidente"],
        "guardrails": ["Números e confianças vêm do núcleo determinístico; a IA só redige.", "Contribuição ≠ causalidade (dito nas limitações)."],
    },
    "resolution": {
        "does": ["Escolhe ações do CATÁLOGO compatíveis com a hipótese principal, estima impacto e risco.",
                 "Propõe as operações; executa apenas as aprovadas (modo simulado).",
                 "Explica o plano em linguagem de negócios (IA opcional)."],
        "triggers": ["Após a investigação, dentro do fluxo do incidente"],
        "guardrails": ["Nunca cria ação fora do catálogo.", "Ações em pedidos, pagamentos, estoque ou clientes sempre exigem aprovação humana."],
    },
    "validation": {
        "does": ["Valida dados antes da investigação (qualidade, amostra).",
                 "Depois da execução, confere política, status e re-mede o indicador."],
        "triggers": ["Início e fim do fluxo do incidente"],
        "guardrails": ["100% regras — não usa IA."],
    },
    "support": {
        "does": ["Tria contatos de WhatsApp, e-mail e Reclame Aqui: intenção, pedido, urgência e recontato.",
                 "Calcula a veracidade da reclamação (0–100) com evidências.",
                 "Decide automático × pessoa pela matriz de Configurações › Atendimento e responde assuntos informativos.",
                 "Propõe ações (chamado, troca, reenvio, reembolso, cancelamento) e trabalha em turnos (SLA, lembretes, picos).",
                 "IA opcional: desempate de intenção (Jev), reescrita da resposta e resumo para quem assume."],
        "triggers": ["Chegada de contatos", "Turno autônomo (agendador ou botão)", "Ações do atendente na caixa"],
        "guardrails": ["Nunca nega uma reclamação: inconsistente vai para uma pessoa.", "Reclame Aqui e urgência alta sempre com pessoa.",
                       "A IA não pode introduzir números, datas ou promessas que não estejam nos dados."],
    },
    "assistant": {
        "does": ["Responde perguntas em linguagem natural (“Pergunte ao GoOps”) chamando ferramentas governadas.",
                 "Escreve a narrativa do briefing diário e dos resumos de setor (IA opcional)."],
        "triggers": ["Pergunta no “Pergunte ao GoOps”", "Geração do briefing", "Agentes de setor com IA"],
        "guardrails": ["Ferramentas rodam com as permissões de quem pergunta.", "Resposta com números sem consulta é descartada."],
    },
}


@dataclass
class AgentContext:
    db: Database
    lake: Lakehouse
    incident_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    is_demo: bool = False
    router: Optional[CostRouter] = None
    events: List[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.router is None:
            self.router = CostRouter(self.db)


class AgentRun:
    """Context manager que registra cada execução de agente em agent_runs."""

    def __init__(self, ctx: AgentContext, agent_key: str, task: str, input_data: Optional[dict] = None):
        self.ctx, self.agent_key, self.task = ctx, agent_key, task
        self.id = new_id("RUN")
        self.principal: Principal = agent_principal(agent_key)
        self.output: Any = None
        ctx.db.execute("INSERT INTO agent_runs (id, agent_key, incident_id, workflow_run_id, task, status, input, started_at) "
                       "VALUES (?, ?, ?, ?, ?, 'running', ?, ?)",
                       (self.id, agent_key, ctx.incident_id, ctx.workflow_run_id, task, jdump(input_data or {}), now_iso()))
        if ctx.incident_id:
            register_agent(ctx.db, ctx.incident_id, agent_key)

    def event(self, event_type: str, message: str, data: Any = None) -> None:
        if self.ctx.incident_id:
            add_event(self.ctx.db, self.ctx.incident_id, self.principal, event_type, message,
                      {**(data or {}), "agent_run_id": self.id} if isinstance(data, dict) or data is None else data,
                      is_demo=self.ctx.is_demo)

    def __enter__(self) -> "AgentRun":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        cost = self.ctx.db.fetchone("SELECT COALESCE(SUM(cost_usd), 0) AS c FROM llm_calls WHERE agent_run_id = ?",
                                    (self.id,))["c"]
        if exc is None:
            self.ctx.db.execute("UPDATE agent_runs SET status = 'success', output = ?, finished_at = ?, cost_usd = ? "
                                "WHERE id = ?", (jdump(self.output), now_iso(), float(cost or 0), self.id))
        else:
            msg = exc.message if isinstance(exc, GoOpsError) else f"{type(exc).__name__}: {str(exc)[:300]}"
            self.ctx.db.execute("UPDATE agent_runs SET status = 'failed', error = ?, finished_at = ?, cost_usd = ? "
                                "WHERE id = ?", (msg, now_iso(), float(cost or 0), self.id))
            self.event("agent_error", f"{AGENT_CATALOG[self.agent_key]['name']} falhou: {msg}",
                       {"trace": traceback.format_exception_only(exc_type, exc)[-1][:300]})
        return False


def agent_stats(db: Database) -> List[dict]:
    from .custom import health_7d
    out = []
    for key, meta in AGENT_CATALOG.items():
        s = db.fetchone("SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END), 0) AS ok, "
                        "COALESCE(SUM(cost_usd), 0) AS cost, MAX(started_at) AS last FROM agent_runs WHERE agent_key = ?",
                        (key,))
        running = db.fetchone("SELECT COUNT(*) AS n FROM agent_runs WHERE agent_key = ? AND status = 'running'", (key,))["n"]
        last = db.fetchone("SELECT id, status, task, started_at, finished_at, incident_id FROM agent_runs "
                           "WHERE agent_key = ? ORDER BY started_at DESC LIMIT 1", (key,))
        out.append({"key": key, **meta, "state": "running" if running else ("idle" if s["n"] else "never_run"),
                    "runs": s["n"], "success_rate": round(s["ok"] / s["n"] * 100, 1) if s["n"] else None,
                    "cost_usd": round(float(s["cost"]), 6), "last_run": last,
                    "permissions": sorted(agent_principal(key).permissions()),
                    "ai_tasks": [s["label"] for s in SLOTS.values() if s["agent"] == key], "health": health_7d(db, key),
                    "drafts": sum(1 for k, sl in SLOTS.items() if sl["agent"] == key and _draft(db, k))})
    return out


def list_agent_runs(db: Database, agent_key: Optional[str] = None, limit: int = 100) -> List[dict]:
    limit = max(1, min(int(limit), 500))
    if agent_key:
        rows = db.fetchall(f"SELECT * FROM agent_runs WHERE agent_key = ? ORDER BY started_at DESC LIMIT {limit}", (agent_key,))
    else:
        rows = db.fetchall(f"SELECT * FROM agent_runs ORDER BY started_at DESC LIMIT {limit}")
    for r in rows:
        r["input"] = jload(r["input"], {})
        r["output"] = jload(r["output"], None)
    return rows
