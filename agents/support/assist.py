"""IA no Atendimento, sempre com regras como plano B:

* `ai_classify` — Jev (AI Proxy Gogroup) decide a intenção de mensagens ambíguas, com probabilidade; abaixo de 0,7
  o caso segue com uma pessoa (o agente "levanta a mão").
* `case_summary` — resumo do caso para quem assume (passagem robô → pessoa e alertas no canal do time). A base é
  determinística (fatos do pedido, veracidade, histórico); com modelo configurado (nível 2), ele só reescreve —
  não pode acrescentar números/datas que não estejam nos fatos.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from goops_core.db import Database
from goops_core.support_catalog import CHANNELS, INTENTS

from . import triage
from agents.instructions import prompt_for


def ai_classify(db: Database, settings, subject: Optional[str], message: str, channel: str,
                agent_run_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    token = getattr(settings, "ai_proxy_api_key", None)
    if not token:
        return None
    from agents.llm.gogroup_proxy import jev
    criteria = {k: v["label"] for k, v in INTENTS.items()}
    try:
        out = jev(db, token, {"canal": CHANNELS.get(channel, channel), "assunto": triage.mask_pii(subject or ""),
                              "mensagem": triage.mask_pii(message)[:1500]},
                  {"intencao": {"type": "choice", "instructions": prompt_for(db, "support_classify").replace("\n", " "),
                                "criteria": criteria}},
                  agent_key="support", task="support_classify", agent_run_id=agent_run_id)
    except Exception:  # noqa: BLE001 - IA indisponível: segue com as regras
        return None
    a = (out["answers"] or {}).get("intencao") or {}
    intent, conf = a.get("choice"), float(a.get("confidence") or 0)
    if intent not in INTENTS:
        return None
    return {"intent": intent, "confidence": round(conf, 2), "model": out.get("model")}


def _facts(c: Dict[str, Any], order: Optional[dict]) -> str:
    ver = c.get("veracity_factors") or {}
    if isinstance(ver, str):
        from goops_core.util import jload
        ver = jload(ver, {}) or {}
    acts = c.get("suggested_actions") or []
    if isinstance(acts, str):
        from goops_core.util import jload
        acts = jload(acts, []) or []
    who = f"Cliente {c['customer_id']}" if c.get("customer_id") else "Contato sem cadastro"
    parts = [f"{who} via {CHANNELS.get(c['channel'], c['channel'])}: {INTENTS.get(c.get('intent') or 'outros', INTENTS['outros'])['label']}"
             + (f" do pedido #{c['order_id']}" if c.get("order_id") else " (sem pedido vinculado)") + "."]
    if order:
        if order.get("delivered_at"):
            parts.append(f"Pedido entregue em {str(order['delivered_at'])[:10]} por {order.get('carrier')}.")
        elif order.get("eta"):
            parts.append(f"Pedido em trânsito com {order.get('carrier')}, previsão {str(order['eta'])[:10]}.")
    if c.get("veracity_label") and c["veracity_label"] != "nao_aplicavel":
        top = sorted((ver.get("factors") or []), key=lambda f: -abs(f.get("points", 0)))[:2]
        parts.append(f"Veracidade {c['veracity_label']} ({c.get('veracity_score')}): " + "; ".join(f["factor"] for f in top) + ".")
    n = int(c.get("contact_number") or 1)
    if n > 1:
        parts.append(f"{n}º contato sobre o assunto.")
    if int(c.get("chase_count") or 0):
        parts.append(f"Cobrou retorno {c['chase_count']} vez(es).")
    if acts:
        parts.append(f"Próximo passo sugerido: {acts[0]['title'].lower()}.")
    elif (ver.get("checks") or []):
        parts.append(f"Próximo passo sugerido: {ver['checks'][0].rstrip('.').lower()}.")
    return " ".join(parts)


def case_summary(db: Database, c: Dict[str, Any], order: Optional[dict], use_llm: bool,
                 agent_run_id: Optional[str] = None) -> Dict[str, str]:
    base = _facts(c, order)
    if not use_llm:
        return {"text": base, "generated_by": "deterministic"}
    from agents.routing.router import CostRouter

    def guard(text: str) -> str:
        t = text.strip()
        if not t or len(t) > 700:
            raise ValueError("resumo inválido")
        if set(re.findall(r"\d+", t)) - set(re.findall(r"\d+", base)):
            raise ValueError("modelo introduziu números que não estão nos fatos")
        return t

    out = CostRouter(db).run(agent_key="support", task="support_summary", deterministic=lambda: base, max_tokens=300,
                             agent_run_id=agent_run_id, postprocess=guard,
                             prompt=lambda: (prompt_for(db, "support_summary") + f"\n<evidence>{base}</evidence>"))
    return {"text": out["output"], "generated_by": out["generated_by"]}
