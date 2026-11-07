"""Investigation Agent — investigação baseada em evidências (núcleo determinístico).

Para uma queda de NPS, decompõe a variação do NPS oficial por dimensão:
    NPS = Σ w_i · NPS_i   =>   ΔNPS = Σ (w_i' · NPS_i' − w_i · NPS_i)
e atribui a cada segmento a sua contribuição. As hipóteses são corroboradas com métricas
operacionais (atraso), temas de comentários, qualidade de dados e lineage. Cada hipótese
traz grau de confiança (heurístico, explicado) e as evidências que a sustentam.
Correlação/contribuição NÃO é prova de causalidade — isso é explicitado nas limitações.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from goops_core.incidents import get_incident, set_status, update_fields

from ..base import AgentContext, AgentRun
from ..instructions import prompt_for
from ..tools.registry import call_tool
from .classify import classify_unthemed

DIMENSIONS = ["carrier", "state", "product_line", "shipping_type"]
DIM_LABEL = {"carrier": "transportadora", "state": "UF", "product_line": "linha de produto", "shipping_type": "tipo de frete"}


def _bounds(months: List[str]) -> Dict[str, str]:
    start = pd.Period(months[0], freq="M").start_time.strftime("%Y-%m-%d")
    end = pd.Period(months[-1], freq="M").end_time.strftime("%Y-%m-%d")
    return {"start": start, "end": end}


def _nps_var(g: Optional[dict]) -> Optional[float]:
    """Variância amostral do NPS (em fração) para teste de diferença: (p+ + p- - (p+ - p-)^2) / n."""
    if not g or not g.get("n"):
        return None
    n = g["n"]
    pp, pd_ = g["promoters"] / n, g["detractors"] / n
    return (pp + pd_ - (pp - pd_) ** 2) / n


def decompose(cur_groups: List[dict], base_groups: List[dict], dim: str) -> List[dict]:
    """Decomposição do ΔNPS (pesos médios, soma exata):
        ΔNPS = Σ w̄ᵢ·ΔNPSᵢ  (efeito desempenho)  +  Σ Δwᵢ·(N̄PSᵢ − N̄PS)  (efeito composição/mix)
    O efeito desempenho isola a piora DENTRO do segmento; o efeito mix reflete mudança de participação."""
    n_cur = sum(g["n"] for g in cur_groups) or 1
    n_base = sum(g["n"] for g in base_groups) or 1
    base = {g[dim]: g for g in base_groups}
    cur = {g[dim]: g for g in cur_groups}
    overall_c = sum(g["n"] * (g["value"] or 0) for g in cur_groups) / n_cur
    overall_b = sum(g["n"] * (g["value"] or 0) for g in base_groups) / n_base
    overall_mid = (overall_c + overall_b) / 2
    out = []
    for key in set(base) | set(cur):
        c, b = cur.get(key), base.get(key)
        wc, wb = (c["n"] / n_cur if c else 0), (b["n"] / n_base if b else 0)
        nc = c["value"] if c and c["value"] is not None else None
        nb = b["value"] if b and b["value"] is not None else None
        if nc is not None and nb is not None:
            rate = (wc + wb) / 2 * (nc - nb)
            mix = (wc - wb) * ((nc + nb) / 2 - overall_mid)
            vc, vb = _nps_var(c), _nps_var(b)
            z = ((nc - nb) / 100) / ((vc + vb) ** 0.5) if vc is not None and vb is not None and (vc + vb) > 0 else None
        else:  # segmento novo ou extinto: só efeito composição
            rate, z = 0.0, None
            mix = (wc - wb) * (((nc if nc is not None else nb) or 0) - overall_mid)
        out.append({"segment": key, "dimension": dim, "n_current": c["n"] if c else 0, "n_baseline": b["n"] if b else 0,
                    "nps_current": nc, "nps_baseline": nb, "weight_current": round(wc, 4), "weight_baseline": round(wb, 4),
                    "rate_effect": round(rate, 3), "mix_effect": round(mix, 3), "contribution": round(rate + mix, 3),
                    "z_score": round(z, 2) if z is not None else None})
    return sorted(out, key=lambda r: r["rate_effect"])


def _confidence(concentration: float, significant: bool, corroborations: int, small_sample: bool,
                dq_issue: bool) -> float:
    """Heurística documentada: concentração da piora (0–0,5) + significância estatística (0,15)
    + corroborações (0,2 + 0,1) − penalidades (amostra pequena 0,15; qualidade de dados 0,1)."""
    conf = 0.5 * max(0.0, min(1.0, concentration)) + (0.15 if significant else 0.0)
    conf += 0.2 * min(corroborations, 1) + 0.1 * max(0, corroborations - 1)
    if small_sample:
        conf -= 0.15
    if dq_issue:
        conf -= 0.1
    return round(min(0.95, max(0.05, conf)), 2)


def _label(c: float) -> str:
    return "alta" if c >= 0.7 else ("média" if c >= 0.4 else "baixa")


def investigate_nps_drop(ctx: AgentContext, run: AgentRun, sig: dict) -> Dict[str, Any]:
    p = run.principal
    cur_p, base_p = _bounds([sig["month"]]), _bounds(sig["baseline_months"])
    total_cur = call_tool(ctx, p, "nps_total", cur_p, run)["result"]
    total_base = call_tool(ctx, p, "nps_total", base_p, run)["result"]
    delta = round((total_cur["value"] or 0) - (total_base["value"] or 0), 2)
    run.event("analysis", f"NPS {sig['month']}: {total_cur['value']} (n={total_cur['n']}) vs. período base "
                          f"{sig['baseline_months'][0]}–{sig['baseline_months'][-1]}: {total_base['value']} "
                          f"(n={total_base['n']}). Δ = {delta:+.2f} pts.",
              {"current": total_cur, "baseline": total_base, "source": "Corporate Gold · gold_nps_analytics"})
    decomp: Dict[str, List[dict]] = {}
    for dim in DIMENSIONS:
        cur = call_tool(ctx, p, "nps_breakdown", {"dimension": dim, **cur_p}, run)["groups"]
        base = call_tool(ctx, p, "nps_breakdown", {"dimension": dim, **base_p}, run)["groups"]
        decomp[dim] = decompose(cur, base, dim)

    dq = call_tool(ctx, p, "data_quality_status", {"datasets": ["silver_nps_evaluations", "silver_deliveries",
                                                                "silver_orders"]}, run)
    errors = [i for i in dq["issues"] if i["severity"] == "error"]
    max_err_rate = max([i["fail_rate"] or 0 for i in errors], default=0)
    dq_issue = max_err_rate > 5
    run.event("data_quality_check", f"Qualidade de dados verificada: {len(dq['issues'])} regras com ocorrências; "
                                    f"maior taxa de erro {max_err_rate}%.", {"issues": dq["issues"][:8]})
    lineage = call_tool(ctx, p, "lineage_upstream", {"node": "metric:METRIC_NPS_001"}, run)
    run.event("lineage_check", "Lineage do indicador consultado (origem até as fontes).", lineage)

    hypotheses: List[dict] = []
    for dim in DIMENSIONS:
        worst = decomp[dim][0] if decomp[dim] else None
        if not worst or worst["rate_effect"] >= 0 or delta >= 0:
            continue
        neg_total = sum(r["rate_effect"] for r in decomp[dim] if r["rate_effect"] < 0) or -1
        share = min(1.0, worst["rate_effect"] / neg_total)          # concentração da piora no segmento
        significant = worst["z_score"] is not None and worst["z_score"] <= -2
        evidence = [{"type": "nps_decomposition", "dimension": dim, **worst,
                     "metric": "METRIC_NPS_001", "dataset": "gold_nps_analytics"}]
        corroborations = 0
        notes: List[str] = []
        if dim == "carrier":
            late_cur = {g["carrier"]: g for g in call_tool(ctx, p, "delivery_late_rate",
                                                            {"group_by": "carrier", **cur_p}, run)["groups"]}
            late_base = {g["carrier"]: g for g in call_tool(ctx, p, "delivery_late_rate",
                                                             {"group_by": "carrier", **base_p}, run)["groups"]}
            lc, lb = late_cur.get(worst["segment"]), late_base.get(worst["segment"])
            if lc and lb and lc["value"] is not None and lb["value"] is not None:
                inc = round(lc["value"] - lb["value"], 2)
                evidence.append({"type": "late_rate_change", "carrier": worst["segment"], "current": lc["value"],
                                 "baseline": lb["value"], "increase_pp": inc, "n_current": lc["n"],
                                 "metric": "METRIC_LATE_DELIVERY_RATE_001", "dataset": "gold_delivery_performance",
                                 "note": "período por data de envio"})
                if inc >= 10:
                    corroborations += 1
                    notes.append(f"taxa de atraso subiu {inc:+.1f} p.p.")
            else:  # fonte sem datas de previsão: corroborar pelo prazo médio de entrega
                dd_cur = {g["carrier"]: g for g in call_tool(ctx, p, "delivery_days", {"group_by": "carrier", **cur_p}, run)["groups"]}
                dd_base = {g["carrier"]: g for g in call_tool(ctx, p, "delivery_days", {"group_by": "carrier", **base_p}, run)["groups"]}
                dc, db_ = dd_cur.get(worst["segment"]), dd_base.get(worst["segment"])
                if dc and db_ and dc["value"] is not None and db_["value"] is not None:
                    inc_d = round(dc["value"] - db_["value"], 2)
                    evidence.append({"type": "delivery_days_change", "carrier": worst["segment"], "current": dc["value"],
                                     "baseline": db_["value"], "increase_days": inc_d, "n_current": dc["n"],
                                     "metric": "METRIC_DELIVERY_DAYS_001", "dataset": "gold_delivery_performance",
                                     "note": "período pela data do pedido"})
                    if inc_d >= 1.5:
                        corroborations += 1
                        notes.append(f"prazo médio de entrega subiu {inc_d:+.1f} dias")
            risk = call_tool(ctx, p, "delay_risk_summary", {"carrier": worst["segment"]}, run)
            evidence.append({"type": "open_delivery_risk", **risk, "dataset": "logistics_delay_risk"})
        filters = {dim: [worst["segment"]]}
        th_cur = call_tool(ctx, p, "comment_themes", {"category": "detractors", **cur_p, "filters": filters}, run)
        th_base = call_tool(ctx, p, "comment_themes", {"category": "detractors", **base_p, "filters": filters}, run)
        top_cur = th_cur["themes"][0] if th_cur["themes"] else None
        if top_cur:
            base_share = next((t["share"] for t in th_base["themes"] if t["theme"] == top_cur["theme"]), 0) or 0
            evidence.append({"type": "comment_themes", "segment": worst["segment"], "top_theme": top_cur["label"],
                             "share_current": top_cur["share"], "share_baseline": base_share,
                             "comments_processed": th_cur["comments_processed"],
                             "dataset": "gold_nps_analytics (NLP determinístico v1.0)"})
            if top_cur["polarity"] == "negative" and (top_cur["share"] or 0) - base_share >= 0.10:
                corroborations += 1
                notes.append(f"tema '{top_cur['label']}' cresceu entre detratores")
        conf = _confidence(share, significant, corroborations, worst["n_current"] < 30, dq_issue)
        hypotheses.append({
            "id": f"H-{dim}",
            "dimension": dim, "segment": worst["segment"],
            "statement": (f"Piora concentrada em {DIM_LABEL[dim]} '{worst['segment']}': NPS do segmento passou de "
                          f"{worst['nps_baseline']:.1f} para {worst['nps_current']:.1f} (efeito de desempenho "
                          f"{worst['rate_effect']:+.2f} pts no NPS geral, {share * 100:.0f}% da piora da dimensão; "
                          f"z = {worst['z_score'] if worst['z_score'] is not None else 'n/d'}"
                          f"{'' if significant else ', diferença NÃO significativa'})"
                          + (f"; {'; '.join(notes)}" if notes else "") + "."),
            "statistically_significant": significant,
            "share_of_drop": round(share, 3), "confidence": conf, "confidence_label": _label(conf),
            "corroborations": corroborations, "evidence": evidence,
        })
    hypotheses.sort(key=lambda h: -h["confidence"])
    if hypotheses:  # nível 1: classificar comentários de detratores sem tema no segmento principal
        top = hypotheses[0]
        cls = classify_unthemed(ctx, run, cur_p, {top["dimension"]: [top["segment"]]})
        top["evidence"].append({"type": "comment_classification", "segment": top["segment"], **cls})
        run.event("analysis", f"Classificação de comentários sem tema ({cls['generated_by']}): "
                              f"{cls.get('classified') or 'nenhum classificado'}; não classificados: {cls['unclassified']}.",
                  {"generated_by": cls["generated_by"], "fallback_reason": cls.get("fallback_reason")})
    if dq_issue:
        hypotheses.append({"id": "H-data-quality", "dimension": "data_quality", "segment": None,
                           "statement": f"Parte da variação pode decorrer de problemas de qualidade de dados "
                                        f"(taxa máxima de erro {max_err_rate}%).",
                           "share_of_drop": None, "confidence": 0.3, "confidence_label": "baixa", "corroborations": 0,
                           "evidence": [{"type": "data_quality", "issues": errors}]})
    limitations = [
        "Decomposição em efeito de desempenho (piora dentro do segmento) e efeito composição (mudança de "
        "participação); contribuição não prova causalidade e dimensões podem estar correlacionadas (ex.: UF e transportadora).",
        "Significância: teste z aproximado da diferença de NPS do segmento entre os períodos (|z| ≥ 2).",
        f"Período atual {sig['month']} comparado à média de {', '.join(sig['baseline_months'])}.",
        "Avaliações de pedidos ainda não entregues não existem; atrasos recentes podem estar sub-representados.",
        f"{len(dq['issues'])} regras de qualidade com ocorrências (registros em quarentena não entram no cálculo).",
    ]
    return {"delta": delta, "current": total_cur, "baseline": total_base, "decomposition": {
        d: v[:5] for d, v in decomp.items()}, "hypotheses": hypotheses, "limitations": limitations,
            "data_quality": {"max_error_rate": max_err_rate, "issues": len(dq["issues"])}, "lineage": lineage}


def investigate_support_spike(ctx: AgentContext, run: AgentRun, sig: dict) -> Dict[str, Any]:
    """Acionado pelo Agente de Atendimento: pico de reclamações de entrega de uma transportadora. Cruza com a taxa de
    atraso (últimos meses de envio), o risco das entregas em aberto e o NPS da transportadora."""
    p = run.principal
    carrier = sig["carrier"]
    months = sorted(g["ship_month"] for g in call_tool(ctx, p, "delivery_late_rate", {"group_by": "ship_month",
                                                                                       "filters": {"carrier": [carrier]}}, run)["groups"]
                    if g["ship_month"] != "Não identificado" and g["n"] >= 10)
    evidence: List[Dict[str, Any]] = [{"type": "support_contacts", "carrier": carrier, "contacts": sig.get("contacts"),
                                       "by_intent": sig.get("by_intent"), "window_hours": sig.get("window_hours", 48)}]
    conf = 0.5
    if len(months) >= 2:
        cur = call_tool(ctx, p, "delivery_late_rate", {"filters": {"carrier": [carrier], "ship_month": [months[-1]]}}, run)
        prv = call_tool(ctx, p, "delivery_late_rate", {"filters": {"carrier": [carrier], "ship_month": [months[-2]]}}, run)
        cv, pv = (cur.get("result") or cur).get("value"), (prv.get("result") or prv).get("value")
        if cv is not None and pv is not None:
            evidence.append({"type": "late_rate_change", "carrier": carrier, "current": cv, "baseline": pv,
                             "increase_pp": round(cv - pv, 2), "metric": "METRIC_LATE_DELIVERY_RATE_001"})
            conf = 0.75 if cv - pv >= 10 else 0.6 if cv > pv else 0.45
    risk = call_tool(ctx, p, "delay_risk_summary", {"carrier": carrier}, run)
    evidence.append({"type": "open_delivery_risk", **risk})
    return {"hypotheses": [{"id": "H-carrier-support", "dimension": "carrier", "segment": carrier,
                            "statement": f"Problema operacional na transportadora {carrier}: {sig.get('contacts')} reclamações de "
                                         f"entrega em {sig.get('window_hours', 48)} h no atendimento.",
                            "share_of_drop": None, "confidence": conf, "confidence_label": _label(conf),
                            "corroborations": len(evidence) - 1, "evidence": evidence}],
            "limitations": ["Contatos de atendimento são sintéticos na demonstração.",
                            "Taxa de atraso do mês corrente é parcial (entregas em trânsito)."]}


def investigate_carrier(ctx: AgentContext, run: AgentRun, sig: dict) -> Dict[str, Any]:
    p = run.principal
    carrier = sig["carrier"]
    cur_p = _bounds([sig["month"]])
    nps_by_carrier = {g["carrier"]: g for g in call_tool(ctx, p, "nps_breakdown", {"dimension": "carrier", **cur_p}, run)["groups"]}
    by_state = call_tool(ctx, p, "delivery_late_rate", {"group_by": "state", **cur_p, "filters": {"carrier": [carrier]}}, run)
    risk = call_tool(ctx, p, "delay_risk_summary", {"carrier": carrier}, run)
    worst_states = sorted([g for g in by_state["groups"] if g["n"] >= 10], key=lambda g: -(g["value"] or 0))[:5]
    evidence = [{"type": "late_rate_change", "carrier": carrier, "current": sig["value"], "baseline": sig["previous_value"],
                 "increase_pp": sig["increase_pp"], "metric": "METRIC_LATE_DELIVERY_RATE_001"},
                {"type": "late_rate_by_state", "states": [{"state": g["state"], "late_rate": g["value"], "n": g["n"]}
                                                          for g in worst_states]},
                {"type": "open_delivery_risk", **risk}]
    if carrier in nps_by_carrier:
        evidence.append({"type": "nps_for_carrier", "nps": nps_by_carrier[carrier]["value"],
                         "n": nps_by_carrier[carrier]["n"], "metric": "METRIC_NPS_001"})
    conf = 0.75 if sig["increase_pp"] >= 30 else 0.55
    return {"hypotheses": [{"id": "H-carrier-ops", "dimension": "carrier", "segment": carrier,
                            "statement": f"Degradação operacional da transportadora {carrier} "
                                         f"({sig['previous_value']}% → {sig['value']}% de atrasos).",
                            "share_of_drop": None, "confidence": conf, "confidence_label": _label(conf),
                            "corroborations": 1, "evidence": evidence}],
            "limitations": ["Mês corrente parcial: entregas ainda em trânsito não entram na taxa."]}


def investigate_product(ctx: AgentContext, run: AgentRun, sig: dict) -> Dict[str, Any]:
    p = run.principal
    period = _bounds(sig["months"])
    themes = call_tool(ctx, p, "comment_themes", {"category": "detractors", **period,
                                                   "filters": {"product_line": [sig["product_line"]]}}, run)
    top = themes["themes"][:3]
    conf = 0.6 if top and top[0]["polarity"] == "negative" else 0.35
    return {"hypotheses": [{"id": "H-product-quality", "dimension": "product_line", "segment": sig["product_line"],
                            "statement": f"Problema de produto/qualidade na linha {sig['product_line']}: temas mais "
                                         f"frequentes entre detratores: " + ", ".join(t["label"] for t in top) + ".",
                            "share_of_drop": None, "confidence": conf, "confidence_label": _label(conf),
                            "corroborations": 1 if top else 0,
                            "evidence": [{"type": "detractor_rate", "value": sig["value"], "overall": sig["overall"],
                                          "ratio": sig["ratio"], "n": sig["n"]},
                                         {"type": "comment_themes", "themes": top,
                                          "comments_processed": themes["comments_processed"]}]}],
            "limitations": ["Temas detectados por dicionário (v1.0); comentários sem tema não são classificados."]}


def _narrative(result: Dict[str, Any]) -> str:
    hs = result["hypotheses"]
    if not hs:
        return "Investigação inconclusiva: nenhuma dimensão explica a variação de forma consistente."
    h = hs[0]
    txt = f"Hipótese principal (confiança {h['confidence_label']}, {h['confidence']:.2f}): {h['statement']}"
    if len(hs) > 1:
        txt += " Hipóteses alternativas: " + "; ".join(f"{x['statement']} (confiança {x['confidence']:.2f})" for x in hs[1:3])
    return txt + " Limitações: " + " ".join(result["limitations"])


def run_investigation(ctx: AgentContext) -> Dict[str, Any]:
    inc = get_incident(ctx.db, ctx.incident_id)
    with AgentRun(ctx, "investigation", "rank_root_causes", {"incident_id": inc["id"]}) as run:
        if inc["status"] in ("detected", "reopened"):
            set_status(ctx.db, inc["id"], "investigating", run.principal, "Agente de Investigação iniciou a análise")
        run.event("investigation_started", "Agente de Investigação iniciou a análise do incidente.")
        sig = inc.get("signal") or {}
        handler = {"nps_drop": investigate_nps_drop, "carrier_late_increase": investigate_carrier,
                   "product_detractors": investigate_product,
                   "support_contact_spike": investigate_support_spike}.get(sig.get("type"))
        if handler is None:
            result = {"hypotheses": [], "limitations": ["Incidente sem sinal estruturado: investigação automática "
                                                        "não aplicável; requer análise humana."]}
        else:
            result = ctx.router.run(agent_key="investigation", task="rank_root_causes",
                                    deterministic=lambda: handler(ctx, run, sig), agent_run_id=run.id)["output"]
        narrative = ctx.router.run(
            agent_key="investigation", task="investigation_narrative", agent_run_id=run.id,
            deterministic=lambda: _narrative(result),
            prompt=lambda: (prompt_for(ctx.db, "investigation_narrative") + "\n<evidence>\n"
                            + str({k: result.get(k) for k in ("hypotheses", "limitations", "delta")})[:12000]
                            + "\n</evidence>"))
        top = result["hypotheses"][0] if result["hypotheses"] else None
        root = top["statement"] if top and top["confidence"] >= 0.5 else (
            f"Inconclusivo — hipótese mais provável: {top['statement']}" if top else "Inconclusivo")
        evidence = [{"hypothesis": h["id"], **e} for h in result["hypotheses"] for e in h["evidence"]]
        update_fields(ctx.db, inc["id"], hypotheses=result["hypotheses"], evidence=evidence, root_cause=root)
        run.event("hypothesis", narrative["output"] if isinstance(narrative["output"], str) else str(narrative["output"]),
                  {"generated_by": narrative["generated_by"], "fallback_reason": narrative.get("fallback_reason"),
                   "hypotheses": [{k: h[k] for k in ("id", "statement", "confidence", "confidence_label")}
                                  for h in result["hypotheses"]], "limitations": result["limitations"]})
        run.output = {"hypotheses": len(result["hypotheses"]), "root_cause": root,
                      "narrative_generated_by": narrative["generated_by"]}
        return {**result, "narrative": narrative}
