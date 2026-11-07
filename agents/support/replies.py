"""Respostas sugeridas ao cliente, montadas SÓ com dados governados (pedido, entrega, protocolo).

Determinísticas por padrão; um modelo pode reescrever o texto sob demanda (tom/clareza) recebendo apenas a resposta-base
e os fatos — nunca promete reparação que dependa de aprovação. Canal Reclame Aqui: resposta pública, sem dados pessoais.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional


def _d(v: Optional[datetime]) -> str:
    return v.strftime("%d/%m") if isinstance(v, datetime) else "—"


def build_reply(*, intent: str, channel: str, ctx: Dict[str, Any], ver: Dict[str, Any], routing: Dict[str, Any]) -> str:
    order = ctx.get("order") or {}
    oid = order.get("order_id")
    carrier = ctx.get("carrier") or "a transportadora"
    eta, delivered = ctx.get("eta"), ctx.get("delivered_at")
    ref = f"pedido #{oid}" if oid else "seu pedido"
    hi = "Olá! " if channel != "reclameaqui" else "Olá. Lamentamos o transtorno. "
    sign = "" if channel == "whatsapp" else "\n\nEquipe de Atendimento"
    label = ver.get("label")
    if routing.get("status") == "awaiting_customer" or (not oid and intent not in ("duvida_produto", "elogio", "outros")):
        body = "Para localizar seu pedido, pode nos informar o número dele (aparece no e-mail de confirmação)?"
    elif intent == "onde_esta_pedido":
        if delivered:
            body = f"O {ref} consta como entregue em {_d(delivered)} por {carrier}. Se não o recebeu, responda esta mensagem."
        elif eta:
            body = f"O {ref} está em trânsito com {carrier}, com previsão de entrega até {_d(eta)}."
        else:
            body = f"O {ref} está em preparação. Avisaremos assim que for enviado."
    elif intent == "atraso_entrega":
        if label == "inconsistente" and eta and not delivered:
            body = f"O {ref} está dentro do prazo, com previsão de entrega até {_d(eta)} ({carrier})."
        elif label == "consistente" and not delivered:
            body = (f"Você tem razão: o {ref} passou da previsão ({_d(eta)}). Já acionamos {carrier} para priorizar a "
                    "entrega e retornaremos com a nova data.")
        elif delivered:
            body = f"O {ref} consta como entregue em {_d(delivered)}. Se houver algum problema, conte para nós."
        else:
            body = f"Estamos verificando a entrega do {ref} com {carrier} e retornamos em breve."
    elif intent == "nao_recebido":
        body = (f"Sentimos muito. Abrimos uma verificação com {carrier} sobre a entrega do {ref} (comprovante e local "
                "de entrega) e retornamos com a solução.")
    elif intent in ("avaria", "defeito", "produto_errado"):
        what = {"avaria": "avaria", "defeito": "defeito", "produto_errado": "divergência no produto"}[intent]
        if "Sem evidência" in {f["factor"] for f in ver.get("factors", [])} or "Foto anterior à entrega" in \
                {f["factor"] for f in ver.get("factors", [])}:
            body = (f"Sentimos muito pela {what} no {ref}. Para seguirmos, pode enviar uma foto do produto e da embalagem "
                    "como chegaram?")
        else:
            body = (f"Sentimos muito pela {what} no {ref}. Recebemos as informações e nossa equipe já está analisando "
                    "a melhor solução (troca ou reenvio). Retornamos em breve.")
    elif intent == "troca_devolucao":
        body = f"Claro! Vamos iniciar a troca/devolução do {ref}. Em seguida enviamos as instruções de postagem."
    elif intent == "cancelamento":
        body = (f"Recebemos o pedido de cancelamento do {ref}. Vamos verificar a situação da entrega e confirmar o "
                "cancelamento e o estorno.")
    elif intent == "status_reembolso":
        body = (f"O estorno do {ref} segue o prazo da operadora do cartão (até 2 faturas). Se não aparecer até lá, "
                "nos avise que verificamos com o financeiro.")
    elif intent == "duvida_produto":
        body = "Obrigado pelo interesse! Enviamos as informações do produto e o prazo de produção na página do item."
    elif intent == "elogio":
        body = "Que alegria ler isso! Obrigado por compartilhar com a gente. 💙"
    else:
        body = "Recebemos sua mensagem e um atendente vai responder em breve."
    if channel == "reclameaqui":
        body = body.replace(ref, "seu pedido") + " Também entraremos em contato pelo canal privado."
    return f"{hi}{body}{sign}"
