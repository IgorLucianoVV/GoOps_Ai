"""Monitor Agent — detecção determinística (nível 0) de anomalias em indicadores governados.

Regras (limiares configuráveis via ambiente):
 R1  Queda de NPS: último mês vs. mês anterior OU vs. média dos 3 meses anteriores >= MONITOR_NPS_DROP_POINTS.
 R2  Aumento da taxa de atraso de uma transportadora (mês de envio) >= MONITOR_CARRIER_LATE_INCREASE_PP p.p.
 R3  Linha de produto com taxa de detratores >= MONITOR_PRODUCT_DETRACTOR_RATIO x a taxa geral (últimos 3 meses).
Todas exigem amostra mínima (MONITOR_MIN_SAMPLE). Incidentes são deduplicados por fingerprint.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from goops_core.runtime_config import effective_settings
from goops_core.incidents import add_event, create_incident

from ..base import AgentContext, AgentRun
from ..tools.registry import call_tool


def _severity(drop: float) -> str:
    return "critical" if drop >= 20 else ("high" if drop >= 12 else ("medium" if drop >= 8 else "low"))


def _month_bounds(month: str) -> Dict[str, str]:
    p = pd.Period(month, freq="M")
    return {"start": p.start_time.strftime("%Y-%m-%d"), "end": p.end_time.strftime("%Y-%m-%d")}


def detect(ctx: AgentContext, run: AgentRun) -> List[Dict[str, Any]]:
    s = effective_settings(ctx.db)
    signals: List[Dict[str, Any]] = []
    principal = run.principal

    # R1 — NPS
    rows = [r for r in call_tool(ctx, principal, "nps_monthly", {}, run)["rows"] if r["has_data"]]
    if len(rows) >= 2:
        last, prev = rows[-1], rows[-2]
        base_rows = rows[-4:-1]
        baseline = round(sum(r["nps"] for r in base_rows) / len(base_rows), 2)
        mom = round(last["nps"] - prev["nps"], 2)
        vs_base = round(last["nps"] - baseline, 2)
        drop = max(-mom, -vs_base)
        if last["total"] >= s.monitor_min_sample and drop >= s.monitor_nps_drop_points:
            signals.append({
                "type": "nps_drop", "metric": "METRIC_NPS_001", "month": last["month"],
                "previous_month": prev["month"], "baseline_months": [r["month"] for r in base_rows],
                "value": last["nps"], "previous_value": prev["nps"], "baseline": baseline,
                "mom_delta": mom, "baseline_delta": vs_base, "drop": round(drop, 2), "n": last["total"],
                "threshold": s.monitor_nps_drop_points,
                "fingerprint": f"nps_drop:{last['month']}", "severity": _severity(drop),
                "category": "customer_experience", "domain": "cx",
                "title": f"Queda de NPS em {last['month']}: {last['nps']} ({vs_base:+.1f} vs. média de 3 meses)",
                "description": (f"NPS oficial (METRIC_NPS_001) de {last['nps']} em {last['month']} com {last['total']} "
                                f"avaliações válidas. Variação vs. mês anterior: {mom:+.2f} pts; vs. média dos 3 meses "
                                f"anteriores ({baseline}): {vs_base:+.2f} pts. Limiar: {s.monitor_nps_drop_points} pts."),
            })

    # R2 — atraso por transportadora (por mês de envio)
    late = call_tool(ctx, principal, "delivery_late_rate", {"group_by": "ship_month"}, run)["groups"]
    months = sorted(g["ship_month"] for g in late if g["ship_month"] != "Não identificado" and g["n"] >= s.monitor_min_sample)
    if len(months) >= 2:
        cur_m, prev_m = months[-1], months[-2]
        cur = {g["carrier"]: g for g in call_tool(ctx, principal, "delivery_late_rate",
                                                   {"group_by": "carrier", "filters": {"ship_month": [cur_m]}}, run)["groups"]}
        prv = {g["carrier"]: g for g in call_tool(ctx, principal, "delivery_late_rate",
                                                   {"group_by": "carrier", "filters": {"ship_month": [prev_m]}}, run)["groups"]}
        for carrier, g in cur.items():
            p = prv.get(carrier)
            if not p or g["value"] is None or p["value"] is None or g["n"] < s.monitor_min_sample:
                continue
            inc = round(g["value"] - p["value"], 2)
            if inc >= s.monitor_carrier_late_increase_pp:
                signals.append({
                    "type": "carrier_late_increase", "metric": "METRIC_LATE_DELIVERY_RATE_001", "carrier": carrier,
                    "month": cur_m, "previous_month": prev_m, "value": g["value"], "previous_value": p["value"],
                    "increase_pp": inc, "n": g["n"], "threshold": s.monitor_carrier_late_increase_pp,
                    "fingerprint": f"carrier_late:{carrier}:{cur_m}",
                    "severity": "high" if inc >= 30 else "medium", "category": "logistics", "domain": "logistics",
                    "title": f"Atrasos da transportadora {carrier} subiram {inc:+.1f} p.p. ({cur_m})",
                    "description": (f"Taxa de entregas atrasadas (METRIC_LATE_DELIVERY_RATE_001) de {carrier}: "
                                    f"{g['value']}% em {cur_m} (n={g['n']}) vs. {p['value']}% em {prev_m}. "
                                    f"Observação: entregas do mês corrente ainda em trânsito não entram na base."),
                })

    # R3 — concentração de detratores por linha de produto (últimos 3 meses com dados)
    if rows:
        window = [r["month"] for r in rows[-3:]]
        period = {"start": _month_bounds(window[0])["start"], "end": _month_bounds(window[-1])["end"]}
        overall = call_tool(ctx, principal, "nps_total", period, run)["result"]
        by_line = call_tool(ctx, principal, "nps_breakdown", {"dimension": "product_line", **period}, run)["groups"]
        base_rate = overall["detractor_pct"] or 0
        for g in by_line:
            if g["product_line"] == "Não identificado" or g["n"] < 50 or not base_rate:
                continue
            ratio = round((g["detractor_pct"] or 0) / base_rate, 2)
            if ratio >= s.monitor_product_detractor_ratio:
                signals.append({
                    "type": "product_detractors", "metric": "METRIC_DETRACTOR_RATE_001",
                    "product_line": g["product_line"], "months": window, "value": g["detractor_pct"],
                    "overall": base_rate, "ratio": ratio, "n": g["n"], "threshold": s.monitor_product_detractor_ratio,
                    "fingerprint": f"product_detractors:{g['product_line']}:{window[-1]}", "severity": "medium",
                    "category": "products", "domain": "products",
                    "title": f"Concentração de detratores na linha {g['product_line']} ({ratio}x a média)",
                    "description": (f"Taxa de detratores de {g['detractor_pct']}% na linha {g['product_line']} "
                                    f"(n={g['n']}) vs. {base_rate}% geral em {window[0]}–{window[-1]}."),
                })
    return signals


def run_monitor(ctx: AgentContext) -> Dict[str, Any]:
    with AgentRun(ctx, "monitor", "detect_anomaly") as run:
        decision = ctx.router.run(agent_key="monitor", task="detect_anomaly", deterministic=lambda: detect(ctx, run),
                                  agent_run_id=run.id)
        signals = decision["output"]
        created, existing = [], []
        for sig in signals:
            res = create_incident(ctx.db, run.principal, title=sig["title"], description=sig["description"],
                                  category=sig["category"], domain=sig["domain"], severity=sig["severity"],
                                  source="monitor_agent", signal=sig, related_metrics=[sig["metric"]],
                                  fingerprint=sig["fingerprint"], is_demo=ctx.is_demo)
            inc = res["incident"]
            if res["created"]:
                add_event(ctx.db, inc["id"], run.principal, "anomaly_detected",
                          "Agente Monitor identificou a anomalia por regra determinística (nível 0).",
                          {"rule": sig["type"], "evidence": {k: v for k, v in sig.items()
                                                             if k not in ("title", "description")}, "agent_run_id": run.id},
                          is_demo=ctx.is_demo)
                created.append(inc["id"])
            else:
                existing.append(inc["id"])
        run.output = {"signals": len(signals), "created": created, "already_open": existing,
                      "generated_by": decision["generated_by"]}
        return run.output
