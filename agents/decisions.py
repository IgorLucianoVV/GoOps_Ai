"""Transparência: COMO cada agente decide (regras, fórmulas e parâmetros VIGENTES) e as últimas decisões reais.

Os textos descrevem a lógica implementada no código de cada agente (monitor/agent.py, investigation/agent.py,
resolution/agent.py, validation/agent.py, support/*). Os parâmetros são lidos da configuração em vigor — o que a tela
mostra é o que o agente usa agora. Nada aqui altera comportamento.
"""
from __future__ import annotations

from typing import Any, Dict, List

from goops_core.db import Database
from goops_core.policies import ACTION_CATALOG, CRITICAL_AREAS
from goops_core.runtime_config import effective_settings, get_section
from goops_core.support_catalog import INTENTS
from goops_core.util import jload


def _p(label: str, value: Any, where: str) -> Dict[str, Any]:
    return {"label": label, "value": value, "where": where}


def _actions(keys: List[str]) -> List[Dict[str, Any]]:
    out = []
    for k in keys:
        a = ACTION_CATALOG[k]
        crit = sorted(set(a["impacted_areas"]) & CRITICAL_AREAS)
        out.append({"key": k, "title": a["title"], "risk": a["risk"], "areas": a["impacted_areas"],
                    "approval": "sempre (área crítica: " + ", ".join(crit) + ")" if crit else "conforme política (padrão: não)"})
    return out


def decision_logic(db: Database, agent_key: str) -> Dict[str, Any]:
    s = effective_settings(db)
    sup = get_section(db, "support")
    mon = "Configurações › Monitor, agendador e retenção"
    att = "Configurações › Atendimento"
    logic: Dict[str, Dict[str, Any]] = {
        "monitor": {
            "summary": "Compara indicadores oficiais mês a mês e abre um incidente quando uma regra passa do limiar com amostra suficiente.",
            "steps": [
                {"title": "R1 · Queda de NPS", "rule": "queda = máx(mês anterior − último mês, média dos 3 meses anteriores − último mês)",
                 "decides": "Abre incidente se queda ≥ limiar e n do mês ≥ amostra mínima. Severidade: ≥20 crítica, ≥12 alta, ≥8 média, senão baixa."},
                {"title": "R2 · Atraso por transportadora", "rule": "aumento = taxa de atraso no último mês de envio − mês anterior (p.p.)",
                 "decides": "Abre incidente por transportadora se aumento ≥ limiar e n ≥ amostra mínima. ≥30 p.p. = alta, senão média."},
                {"title": "R3 · Detratores por linha", "rule": "razão = % detratores da linha ÷ % detratores geral (últimos 3 meses)",
                 "decides": "Abre incidente se razão ≥ limiar e n ≥ 50."},
                {"title": "Sem duplicar", "rule": "fingerprint = tipo + segmento + mês",
                 "decides": "Se já existe incidente com o mesmo fingerprint, não abre outro."},
            ],
            "params": [_p("Queda de NPS (pts)", s.monitor_nps_drop_points, mon), _p("Amostra mínima", s.monitor_min_sample, mon),
                       _p("Aumento de atraso (p.p.)", s.monitor_carrier_late_increase_pp, mon),
                       _p("Razão de detratores", s.monitor_product_detractor_ratio, mon),
                       _p("Investigar automaticamente", "sim" if s.auto_investigate else "não", mon)],
            "human": ["Não decide ação nenhuma: só abre o incidente com os números e o limiar usados."],
            "ai": "Não usa IA.",
        },
        "investigation": {
            "summary": "Explica a variação com estatística: decompõe o ΔNPS por dimensão, testa significância e corrobora com outras fontes.",
            "steps": [
                {"title": "Decomposição", "rule": "ΔNPS = Σ w̄ᵢ·ΔNPSᵢ (efeito desempenho) + Σ Δwᵢ·(N̄PSᵢ − N̄PS) (efeito composição)",
                 "decides": "Em cada dimensão (transportadora, UF, linha, frete) pega o segmento com maior efeito de desempenho negativo."},
                {"title": "Significância", "rule": "z = (NPS atual − NPS base) ÷ √(var atual + var base), var = (p⁺ + p⁻ − (p⁺ − p⁻)²) ÷ n",
                 "decides": "Significativo se z ≤ −2."},
                {"title": "Corroboração", "rule": "atraso +10 p.p. (ou prazo +1,5 dia) · tema negativo entre detratores +10 p.p.",
                 "decides": "Cada fonte independente que confirma aumenta a confiança."},
                {"title": "Confiança (0,05–0,95)",
                 "rule": "0,5·concentração + 0,15·[z ≤ −2] + 0,2·[1ª corroboração] + 0,1·[2ª] − 0,15·[n < 30] − 0,1·[erro de dados > 5%]",
                 "decides": "Ordena as hipóteses. ≥ 0,7 alta · ≥ 0,4 média · abaixo baixa. Causa provável só é afirmada com ≥ 0,5."},
            ],
            "params": [_p("Limiar de significância", "|z| ≥ 2", "fixo no código"), _p("Corroboração de atraso", "+10 p.p.", "fixo no código"),
                       _p("Corroboração de tema", "+10 p.p. de participação", "fixo no código")],
            "human": ["Hipótese abaixo de 0,5 aparece como “Inconclusivo”.", "Limitações sempre listadas: contribuição não é causa."],
            "ai": "Opcional: só escreve a narrativa (nível 3) e classifica comentários sem tema numa lista fechada (nível 1).",
        },
        "resolution": {
            "summary": "Transforma as hipóteses com confiança suficiente em ações do CATÁLOGO, com impacto estimado e premissas.",
            "steps": [
                {"title": "Filtro", "rule": "usa até 2 hipóteses com confiança ≥ 0,4", "decides": "Abaixo disso, recomenda análise humana."},
                {"title": "Mapeamento", "rule": "transportadora → realocar volume + contato proativo · linha → revisão de qualidade · "
                                                "UF/frete → revisão regional · dados → correção de qualidade",
                 "decides": "Destino da realocação = transportadora com menor taxa de atraso (n ≥ 30)."},
                {"title": "Impacto", "rule": "pontos recuperáveis = −efeito de desempenho do segmento",
                 "decides": "Premissa explícita: o segmento volta ao patamar do período base, mantido o mix."},
                {"title": "Política", "rule": "área crítica ∈ {" + ", ".join(sorted(CRITICAL_AREAS)) + "} ⇒ aprovação humana",
                 "decides": "Ações críticas ficam aguardando aprovação; execução só após aprovação e em modo simulado."},
            ],
            "params": [_p("Confiança mínima", 0.4, "fixo no código"), _p("Fatia realocada", "30%", "fixo no código")],
            "actions": _actions(["carrier_reallocation", "proactive_customer_contact", "product_quality_review",
                                 "regional_logistics_review", "data_quality_fix"]),
            "human": ["Nunca aprova; agentes e sistema não têm permissão de aprovação.", "Quem aprova precisa do papel e do domínio certos."],
            "ai": "Opcional: só explica o plano em linguagem de negócios (nível 3).",
        },
        "validation": {
            "summary": "Confere os dados antes da investigação e, depois da execução, a política e o efeito no indicador.",
            "steps": [
                {"title": "Antes", "rule": "maior taxa de erro de qualidade ≤ 5% e Gold de NPS construída",
                 "decides": "Se falhar, a investigação segue com ressalva registrada."},
                {"title": "Política", "rule": "toda ação executada que exigia aprovação foi aprovada por um usuário",
                 "decides": "Se não, marca VIOLAÇÃO de política."},
                {"title": "Efeito", "rule": "resolvido se NPS do mês seguinte ≥ valor do incidente + 50% da queda",
                 "decides": "Sem mês posterior, o incidente fica em monitoramento."},
            ],
            "params": [_p("Erro máximo de dados", "5%", "fixo no código"), _p("Recuperação mínima", "50% da queda", "fixo no código")],
            "human": ["Não fecha incidente sem dado posterior que comprove a recuperação."],
            "ai": "Não usa IA.",
        },
        "supervisor": {
            "summary": "Orquestra o fluxo do incidente como um grafo com estado salvo e pausa obrigatória para decisão humana.",
            "steps": [
                {"title": "Fluxo", "rule": "validar dados → investigar → planejar → (aguardar aprovação ⏸) → executar → validar → finalizar",
                 "decides": "Prioriza incidentes por severidade; retoma o grafo quando a pessoa aprova ou rejeita."},
                {"title": "Resumo", "rule": "título + causa provável + ações + resultado", "decides": "Texto final do incidente."},
            ],
            "params": [_p("Investigar automaticamente", "sim" if s.auto_investigate else "não", mon)],
            "human": ["Para no estado “aguardando aprovação” até uma pessoa decidir."],
            "ai": "Opcional: reescreve o resumo executivo (nível 2).",
        },
        "support": {
            "summary": "Tria cada contato com regras explicáveis e decide se resolve sozinho ou se precisa de uma pessoa.",
            "steps": [
                {"title": "Intenção", "rule": "pontuação por padrões de texto; confiança = 0,5 + margem entre 1ª e 2ª intenção (0,35–0,98)",
                 "decides": "Abaixo da confiança mínima → pessoa. Com AI Proxy, o Jev desempata e só vale com confiança ≥ 0,7."},
                {"title": "Urgência", "rule": "pontos: Reclame Aqui +3 · Procon/Justiça +4 · muito negativo +2 · 3º contato +3 · atraso 7+ dias +2 · valor ≥ R$ 300 +1",
                 "decides": "≥7 crítica · ≥4 alta · ≥2 média · senão baixa. Prioridade = pontos × 11 (+5)."},
                {"title": "Veracidade (0–100)", "rule": "50 + Σ fatores (ex.: atraso confirmado +40, foto anterior à entrega −35, reclamações em série −20)",
                 "decides": f"≥ {sup.get('veracity_consistent_min', 70)} consistente · ≤ {sup.get('veracity_inconsistent_max', 39)} inconsistente · meio-termo inconclusiva. Inconsistente vai para pessoa — nunca é negada."},
                {"title": "Automático × pessoa", "rule": "qualquer motivo da lista abaixo ⇒ pessoa; nenhum ⇒ responde sozinho com dados do pedido",
                 "decides": "Os motivos ficam gravados no atendimento."},
                {"title": "Turno", "rule": "lembra e encerra por inatividade · alerta SLA · cobra aprovações · pico por transportadora ⇒ incidente",
                 "decides": "Pico = reclamações de entrega da mesma transportadora em 48 h ≥ limiar ⇒ Supervisor → Investigação."},
            ],
            "params": [
                _p("Intenções automáticas", ", ".join(INTENTS[i]["label"] for i in sup.get("auto_intents", []) if i in INTENTS), att),
                _p("Confiança mínima", sup.get("min_confidence"), att), _p("Canais sempre com pessoa", ", ".join(sup.get("human_channels", [])), att),
                _p("Urgência que vai para pessoa", f"a partir de {sup.get('human_from_urgency')}", att),
                _p("Valor de reclamação para pessoa (R$)", sup.get("claim_value_human_brl"), att),
                _p("Recontato vai para pessoa", "sim" if sup.get("repeat_to_human", True) else "não", att),
                _p("Chamado na transportadora automático", "sim" if sup.get("auto_carrier_ticket", True) else "não", att),
                _p("SLA 1ª resposta (h)", sup.get("sla_first_response_hours"), att), _p("Pico por transportadora", sup.get("spike_min_contacts"), att),
                _p("Encerrar por inatividade (h)", sup.get("inactivity_close_hours"), att)],
            "human": ["Tentativa de manipulação de instruções na mensagem", "Intenção fora das automáticas ou incerta",
                      "Reclame Aqui", "Urgência alta ou crítica", "Recontato", "Reclamação em pedido acima do valor configurado",
                      "Atraso de 7+ dias", "Veracidade inconsistente"],
            "actions": _actions(["support_carrier_ticket", "support_proactive_notice", "support_exchange", "support_cancel_order",
                                 "support_reshipment", "support_refund"]),
            "ai": "Opcional: desempate de intenção (Jev), reescrita da resposta e resumo para quem assume — sem números novos.",
        },
        "assistant": {
            "summary": "Responde perguntas chamando ferramentas governadas (só leitura) com as permissões de quem pergunta.",
            "steps": [
                {"title": "Ferramentas", "rule": "métricas oficiais, valores de dimensões, temas de comentários, qualidade e incidentes",
                 "decides": "O modelo escolhe a ferramenta; o código executa com as permissões do usuário."},
                {"title": "Guarda", "rule": "resposta com números sem nenhuma consulta é descartada",
                 "decides": "Cai no motor determinístico, que responde com as mesmas métricas."},
            ],
            "params": [_p("Etapas máximas", 6, "fixo no código"), _p("Limite por execução (US$)", s.cost_limit_per_run_usd, "Configurações › Modelos e chaves"),
                       _p("Limite diário (US$)", s.cost_limit_daily_usd, "Configurações › Modelos e chaves")],
            "human": ["Não executa ações; só responde."],
            "ai": "Usa IA quando há modelo de nível 3/2; senão, motor determinístico rotulado.",
        },
    }
    return logic.get(agent_key, {})


def recent_decisions(db: Database, agent_key: str, limit: int = 6) -> List[Dict[str, Any]]:
    """Exemplos reais e recentes de decisões do agente, com os números e motivos registrados."""
    out: List[Dict[str, Any]] = []
    if agent_key in ("monitor", "supervisor", "investigation", "resolution", "validation"):
        for i in db.fetchall("SELECT id, title, severity, status, source, signal, hypotheses, root_cause, result, detected_at "
                             "FROM incidents ORDER BY detected_at DESC LIMIT ?", (limit,)):
            sig, hyps, res = jload(i["signal"], {}) or {}, jload(i["hypotheses"], []) or [], jload(i["result"], {}) or {}
            if agent_key == "monitor":
                if i["source"] != "monitor_agent":
                    continue
                why = {"nps_drop": lambda: f"queda {sig.get('drop')} pts ≥ limiar {sig.get('threshold')} (n {sig.get('n')})",
                       "carrier_late_increase": lambda: f"+{sig.get('increase_pp')} p.p. ≥ limiar {sig.get('threshold')} (n {sig.get('n')})",
                       "product_detractors": lambda: f"razão {sig.get('ratio')}× ≥ limiar {sig.get('threshold')} (n {sig.get('n')})"}
                detail = why.get(sig.get("type"), lambda: "")()
            elif agent_key == "investigation":
                if not hyps:
                    continue
                h = hyps[0]
                detail = f"hipótese principal {h.get('segment')} · confiança {h.get('confidence')} ({h.get('confidence_label')})" + \
                         (" · significativa" if h.get("statistically_significant") else "")
            elif agent_key == "resolution":
                ops = db.fetchall("SELECT title, status, requires_approval FROM operations WHERE incident_id = ?", (i["id"],))
                if not ops:
                    continue
                detail = "; ".join(f"{o['title']} ({'exige aprovação' if o['requires_approval'] else 'sem aprovação'} · {o['status']})" for o in ops)
            elif agent_key == "validation":
                if not res:
                    continue
                detail = f"status {res.get('status')} · políticas {'respeitadas' if res.get('policies_ok') else 'com violação' if res.get('policies_ok') is False else 'n/d'}"
            else:
                detail = f"status {i['status']} · causa: {i['root_cause'] or 'em análise'}"
            out.append({"at": i["detected_at"], "title": i["title"], "decision": detail, "link": f"/incidents/{i['id']}"})
    elif agent_key == "support":
        for c in db.fetchall("SELECT id, external_id, channel, intent, intent_confidence, urgency, veracity_score, veracity_label, "
                             "routing, routing_reasons, status, received_at FROM support_contacts WHERE triaged_at IS NOT NULL "
                             "ORDER BY received_at DESC LIMIT ?", (limit,)):
            rr = jload(c["routing_reasons"], {}) or {}
            reasons = rr.get("reasons", []) if isinstance(rr, dict) else rr
            ver = f" · veracidade {c['veracity_score']} ({c['veracity_label']})" if c["veracity_score"] is not None else ""
            out.append({"at": c["received_at"], "title": f"{c['external_id']} · {INTENTS.get(c['intent'], {}).get('label', c['intent'])}",
                        "decision": f"{'pessoa' if c['routing'] == 'human' else 'automático'} · confiança {c['intent_confidence']} · "
                                    f"urgência {c['urgency']}{ver} — {reasons[0] if reasons else ''}",
                        "link": f"/atendimento/{c['id']}"})
    if not out:
        for d in db.fetchall("SELECT task, requested_level, used_level, used_llm, reason, created_at FROM routing_decisions "
                             "WHERE agent_key = ? ORDER BY created_at DESC LIMIT ?", (agent_key, limit)):
            out.append({"at": d["created_at"], "title": d["task"],
                        "decision": f"nível pedido {d['requested_level']} → usado {d['used_level']} — {d['reason']}", "link": None})
    return out[:limit]
