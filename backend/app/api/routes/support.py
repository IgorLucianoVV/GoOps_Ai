"""Atendimento ao Cliente (Desafio 1): caixa unificada, triagem, veracidade, ações e prevenção de recontato."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from goops_core.db import Database
from goops_core.permissions import Principal
from goops_core.support_catalog import CHANNELS, INTENTS, STATUSES, SYSTEMS
from data_platform.storage import Lakehouse
from agents.support import prevention, service
from agents.support.overview import build_overview

from ..deps import db_dep, lake_dep, ok, require

router = APIRouter(prefix="/support", tags=["support"])


class ReplyBody(BaseModel):
    text: str = Field(min_length=5, max_length=4000)
    resolve: bool = True


class ActionBody(BaseModel):
    action_type: str = Field(max_length=60)
    note: str = Field(default="", max_length=500)


class ContactUpdate(BaseModel):
    status: Optional[str] = Field(default=None, max_length=30)
    assign_to_me: bool = False
    intent: Optional[str] = Field(default=None, max_length=40)
    order_id: Optional[str] = Field(default=None, max_length=40)
    note: Optional[str] = Field(default=None, max_length=1000)


class SimulateBody(BaseModel):
    count: int = Field(default=12, ge=1, le=50)


@router.get("/catalog")
def catalog(p: Principal = Depends(require("analytics:read"))):
    return ok({"intents": {k: {"label": v["label"], "claim": v["claim"]} for k, v in INTENTS.items()},
               "channels": CHANNELS, "statuses": STATUSES, "systems": SYSTEMS})


@router.get("/overview")
def overview(p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep)):
    return ok(build_overview(db, p))


@router.get("/contacts")
def contacts(status: Optional[str] = None, channel: Optional[str] = None, intent: Optional[str] = None,
             routing: Optional[str] = None, urgency: Optional[str] = None, veracity: Optional[str] = None,
             q: Optional[str] = Query(default=None, max_length=60), queue: Optional[str] = None, sort: str = "priority",
             limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
             p: Principal = Depends(require("support:read")), db: Database = Depends(db_dep)):
    return ok(service.list_contacts(db, p, status=status, channel=channel, intent=intent, routing_=routing, urgency=urgency,
                                    veracity_label=veracity, q=q, queue=queue, sort=sort, limit=limit, offset=offset))


@router.get("/contacts/{contact_id}")
def contact(contact_id: str, p: Principal = Depends(require("support:read")), db: Database = Depends(db_dep),
            lake: Lakehouse = Depends(lake_dep)):
    return ok(service.get_contact(db, lake, p, contact_id))


@router.post("/contacts/{contact_id}/reply")
def reply(contact_id: str, body: ReplyBody, p: Principal = Depends(require("support:write")), db: Database = Depends(db_dep)):
    return ok(service.send_reply(db, p, contact_id, body.text, body.resolve))


@router.post("/contacts/{contact_id}/draft-ai")
def draft_ai(contact_id: str, p: Principal = Depends(require("support:write")), db: Database = Depends(db_dep),
             lake: Lakehouse = Depends(lake_dep)):
    return ok(service.draft_reply_ai(db, lake, p, contact_id))


@router.post("/contacts/{contact_id}/actions")
def action(contact_id: str, body: ActionBody, p: Principal = Depends(require("support:write")),
           db: Database = Depends(db_dep)):
    return ok(service.propose_action(db, p, contact_id, body.action_type, body.note))


@router.post("/contacts/{contact_id}/update")
def update(contact_id: str, body: ContactUpdate, p: Principal = Depends(require("support:write")),
           db: Database = Depends(db_dep)):
    return ok(service.update_contact(db, p, contact_id, status=body.status, assign_to_me=body.assign_to_me,
                                     intent=body.intent, order_id=body.order_id, note=body.note))


@router.post("/contacts/{contact_id}/retriage")
def retriage(contact_id: str, p: Principal = Depends(require("support:write")), db: Database = Depends(db_dep),
             lake: Lakehouse = Depends(lake_dep)):
    return ok(service.retriage(db, lake, p, contact_id))


@router.get("/prevention")
def prevention_view(p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep),
                    lake: Lakehouse = Depends(lake_dep)):
    return ok({"recontact": prevention.recontact_analysis(db), "root_causes": prevention.root_causes(db, lake),
               "proactive": prevention.proactive_candidates(db, lake)})


@router.post("/prevention/notify")
def prevention_notify(p: Principal = Depends(require("support:write")), db: Database = Depends(db_dep)):
    return ok(prevention.propose_proactive_notice(db, p))


@router.post("/simulate")
def simulate(body: SimulateBody = SimulateBody(), p: Principal = Depends(require("support:write")),
             db: Database = Depends(db_dep), lake: Lakehouse = Depends(lake_dep)):
    from data_platform.support.pipeline import simulate_incoming
    return ok(simulate_incoming(db, lake, p, body.count))


# ------------------------------------------------------------------ conversas (chat unificado estilo WhatsApp)
class NoteBody(BaseModel):
    text: str = Field(min_length=2, max_length=2000)
    contact_id: Optional[str] = Field(default=None, max_length=40)


@router.get("/conversations")
def conversations(queue: Optional[str] = "open", channel: Optional[str] = None, urgency: Optional[str] = None,
                  intent: Optional[str] = None, q: Optional[str] = Query(default=None, max_length=60), sort: str = "priority",
                  limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
                  p: Principal = Depends(require("support:read")), db: Database = Depends(db_dep)):
    from agents.support.conversations import list_conversations
    return ok(list_conversations(db, p, queue=queue, channel=channel, urgency=urgency, intent=intent, q=q, sort=sort,
                                 limit=limit, offset=offset))


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: str, p: Principal = Depends(require("support:read")), db: Database = Depends(db_dep)):
    from agents.support.conversations import get_conversation
    return ok(get_conversation(db, p, conversation_id))


@router.post("/conversations/{conversation_id}/note")
def conversation_note(conversation_id: str, body: NoteBody, p: Principal = Depends(require("support:write")),
                      db: Database = Depends(db_dep)):
    from agents.support.conversations import add_note
    return ok(add_note(db, p, conversation_id, body.text, body.contact_id))


# ------------------------------------------------------------------ turno autônomo e canal do time
class ShiftBody(BaseModel):
    advance_hours: float = Field(default=0, ge=0, le=168)


@router.get("/shift")
def shift_info(p: Principal = Depends(require("analytics:read")), db: Database = Depends(db_dep)):
    from agents.support.shift import shift_status
    return ok(shift_status(db))


@router.post("/shift")
def shift_run(body: ShiftBody = ShiftBody(), p: Principal = Depends(require("support:write")), db: Database = Depends(db_dep),
              lake: Lakehouse = Depends(lake_dep)):
    from agents.support.shift import run_shift
    return ok(run_shift(db, lake, p, body.advance_hours))


team = APIRouter(prefix="/team", tags=["team"])


@team.get("/feed")
def team_feed(limit: int = Query(default=100, ge=1, le=300), p: Principal = Depends(require("operations:read")),
              db: Database = Depends(db_dep)):
    from agents.team_channel import feed
    return ok(feed(db, p, limit))


@team.post("/link-code")
def team_link_code(p: Principal = Depends(require("operations:read")), db: Database = Depends(db_dep)):
    from agents.team_channel import link_code
    return ok(link_code(db, p))


@team.post("/test")
def team_test(p: Principal = Depends(require("settings:write")), db: Database = Depends(db_dep)):
    from agents.team_channel import test_channel
    return ok(test_channel(db, p))
