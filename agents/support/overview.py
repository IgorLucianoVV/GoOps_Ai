"""Visão geral do Atendimento: volume, automação, veracidade, recontato, esforço e acurácia (na base sintética)."""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from goops_core.db import Database
from goops_core.permissions import Principal, require_permission
from goops_core.support_catalog import CHANNELS, INTENTS, SYSTEMS
from goops_core.util import jload


def _minutes(a: pd.Series, b: pd.Series) -> pd.Series:
    return (pd.to_datetime(b, errors="coerce") - pd.to_datetime(a, errors="coerce")).dt.total_seconds() / 60


def build_overview(db: Database, actor: Principal) -> Dict[str, Any]:
    require_permission(actor, "analytics:read")
    rows = db.fetchall("SELECT id, channel, intent, received_at, status, routing, urgency, is_claim, veracity_label, is_repeat, "
                       "avoidable, manual_minutes, saved_minutes, first_response_at, resolved_at, systems_touched, "
                       "history_simulated, is_demo, simulation_truth, injection_suspected FROM support_contacts WHERE status <> 'new'")
    if not rows:
        return {"total": 0, "ready": False}
    df = pd.DataFrame(rows)
    for b in ("is_claim", "is_repeat", "avoidable", "history_simulated", "is_demo", "injection_suspected"):
        df[b] = df[b].astype(bool)
    df["month"] = df["received_at"].str[:7]
    df["frt"] = _minutes(df["received_at"], df["first_response_at"])
    df["res_h"] = _minutes(df["received_at"], df["resolved_at"]) / 60
    df["n_systems"] = df["systems_touched"].map(lambda s: len(jload(s, []) or []))
    total = len(df)
    auto = df[df["routing"] == "auto"]
    human = df[df["routing"] == "human"]
    claims = df[df["is_claim"]]
    open_q = df[df["status"].isin(["pending_human", "pending_approval", "awaiting_customer"])]
    manual_h = float(df["manual_minutes"].sum()) / 60
    saved_h = float(df["saved_minutes"].sum()) / 60
    months = sorted(df["month"].unique())
    per_month = (df.groupby("month").agg(contacts=("id", "count"),
                                         auto=("routing", lambda s: int((s == "auto").sum())),
                                         repeats=("is_repeat", "sum"),
                                         manual_h=("manual_minutes", lambda s: round(float(s.sum()) / 60, 1)),
                                         saved_h=("saved_minutes", lambda s: round(float(s.sum()) / 60, 1)))
                 .reset_index())
    per_month["repeats"] = per_month["repeats"].astype(int)
    per_month["auto_rate"] = (per_month["auto"] / per_month["contacts"] * 100).round(1)
    by_intent = (df.groupby("intent").agg(contacts=("id", "count"), auto=("routing", lambda s: int((s == "auto").sum())))
                 .reset_index().sort_values("contacts", ascending=False))
    by_intent["label"] = by_intent["intent"].map(lambda i: INTENTS.get(i, {}).get("label", i))
    systems = {}
    for s in df["systems_touched"]:
        for k in jload(s, []) or []:
            systems[k] = systems.get(k, 0) + 1
    # acurácia na base SINTÉTICA (gabarito do gerador; nunca usado pela triagem)
    accuracy = None
    truth = df[df["is_demo"] & df["simulation_truth"].notna()].copy()
    if len(truth):
        t = truth["simulation_truth"].map(lambda s: jload(s, {}) or {})
        truth["t_intent"] = t.map(lambda x: x.get("intent"))
        truth["t_genuine"] = t.map(lambda x: x.get("genuine"))
        intent_acc = float((truth["intent"] == truth["t_intent"]).mean() * 100)
        cl = truth[truth["is_claim"] & truth["t_genuine"].notna()]
        fake = cl[cl["t_genuine"] == False]  # noqa: E712
        flagged = cl[cl["veracity_label"] == "inconsistente"]
        accuracy = {"intent_accuracy_pct": round(intent_acc, 1), "claims_evaluated": int(len(cl)),
                    "fake_claims": int(len(fake)),
                    "fake_flagged_pct": round(float((fake["veracity_label"] != "consistente").mean() * 100), 1) if len(fake) else None,
                    "flag_precision_pct": round(float((flagged["t_genuine"] == False).mean() * 100), 1) if len(flagged) else None,  # noqa: E712
                    "genuine_consistent_pct": round(float((cl[cl["t_genuine"] == True]["veracity_label"] == "consistente").mean() * 100), 1)  # noqa: E712
                    if len(cl[cl["t_genuine"] == True]) else None,  # noqa: E712
                    "note": "Medido contra o gabarito do gerador sintético; indica coerência das regras, não desempenho em produção."}
    conv_n = db.fetchone("SELECT COUNT(*) AS n FROM support_conversations")["n"]
    msg_n = db.fetchone("SELECT COUNT(*) AS n FROM support_messages WHERE direction = 'in'")["n"]
    chases = db.fetchone("SELECT COALESCE(SUM(chase_count), 0) AS n FROM support_contacts")["n"]
    return {
        "ready": True, "total": total, "conversations": conv_n, "inbound_messages": msg_n, "chases": int(chases or 0), "months": months, "is_demo": bool(df["is_demo"].any()),
        "history_simulated": int(df["history_simulated"].sum()),
        "per_month": per_month.to_dict("records"),
        "avg_contacts_per_month": round(total / max(1, len(months)), 0),
        "by_channel": [{"channel": c, "label": CHANNELS.get(c, c), "contacts": int(n)}
                       for c, n in df["channel"].value_counts().items()],
        "by_intent": by_intent.to_dict("records"),
        "automation": {"auto": int(len(auto)), "human": int(len(human)),
                       "auto_rate": round(len(auto) / total * 100, 1),
                       "auto_resolved": int((df["status"] == "auto_resolved").sum())},
        "queue": {"open": int(len(open_q)), "by_urgency": open_q["urgency"].value_counts().to_dict(),
                  "by_status": open_q["status"].value_counts().to_dict()},
        "claims": {"total": int(len(claims)), "by_veracity": claims["veracity_label"].value_counts().to_dict(),
                   "inconsistent_rate": round(float((claims["veracity_label"] == "inconsistente").mean() * 100), 1)
                   if len(claims) else None},
        "recontact": {"repeats": int(df["is_repeat"].sum()), "rate": round(float(df["is_repeat"].mean() * 100), 1),
                      "avoidable": int(df["avoidable"].sum()), "avoidable_rate": round(float(df["avoidable"].mean() * 100), 1)},
        "effort": {"manual_hours": round(manual_h, 1), "saved_hours": round(saved_h, 1),
                   "remaining_hours": round(manual_h - saved_h, 1),
                   "saved_pct": round(saved_h / manual_h * 100, 1) if manual_h else None,
                   "avg_systems_per_contact": round(float(df["n_systems"].mean()), 2),
                   "systems": [{"key": k, "label": SYSTEMS[k], "contacts": v} for k, v in
                               sorted(systems.items(), key=lambda kv: -kv[1])],
                   "assumption": "Esforço manual de referência por assunto (Configurações › Atendimento); automação "
                                 "poupa o contato inteiro; casos humanos chegam triados com visão 360 (≈35% do tempo)."},
        "response": {"first_response_auto_min": _med(auto["frt"]), "first_response_human_min": _med(human["frt"]),
                     "resolution_human_h": _med(human["res_h"])},
        "security": {"injection_flagged": int(df["injection_suspected"].sum())},
        "accuracy": accuracy,
    }


def _med(s: pd.Series):
    s = s.dropna()
    return round(float(s.median()), 1) if len(s) else None
