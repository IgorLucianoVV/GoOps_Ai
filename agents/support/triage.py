"""Triagem determinística de contatos: intenção, vínculo com pedido, sentimento e urgência.

Regras explicáveis em português (sem LLM). Um modelo pode ser usado opcionalmente apenas para desempatar intenções de
baixa confiança, e sua saída é validada contra a lista fechada de intenções (ver service.classify_with_llm).
O texto do cliente é sempre tratado como DADO.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from data_platform.analytics.nlp import injection_suspected, normalize
from goops_core.support_catalog import INTENTS

# (padrão sobre texto normalizado — minúsculas e sem acento —, peso). Pesos maiores para pedidos explícitos de ação.
INTENT_RULES: Dict[str, List[Tuple[str, float]]] = {
    "nao_recebido": [(r"(consta|aparece|diz que foi|esta como|marcado como|rastreio diz).{0,40}entregue", 3.0),
                     (r"nao (recebi|chegou aqui|foi recebido)(?! (atualizac|resposta|retorno|informac|nada|o codigo|e.?mail))", 1.6), (r"nunca chegou", 2.0), (r"ninguem assinou", 1.5)],
    "avaria": [(r"quebrad", 2.4), (r"amassad", 2.2), (r"avariad", 2.6), (r"danificad", 2.2), (r"riscad", 1.6),
               (r"trincad", 2.2), (r"rachad", 2.0), (r"caixa .{0,20}(danificada|amassada|rasgada)", 1.4)],
    "defeito": [(r"defeito", 2.6), (r"parou de funcionar", 2.6), (r"nao (veda|funciona|liga|fecha)", 2.0),
                (r"descascand", 2.0), (r"vazand", 1.8), (r"estragou", 1.6)],
    "produto_errado": [(r"(personalizacao|nome|cor|modelo|produto).{0,60}(errad|diferente|trocad|incorret)", 3.0),
                       (r"(errad|incorret)[ao]s?.{0,20}(personalizacao|produto|nome)", 2.6),
                       (r"diferente do (que )?(comprei|comprado|solicitado|pedido)", 2.6), (r"veio trocad", 2.2)],
    "atraso_entrega": [(r"atrasad", 2.2), (r"atraso", 2.0), (r"passou (muito )?do prazo", 2.4), (r"previsao (era|de entrega era)", 2.0),
                       (r"nova (data|previsao)", 1.2), (r"(vou|vai) perder a data", 1.2), (r"demorou demais", 0.8)],
    "onde_esta_pedido": [(r"cade (o )?meu pedido", 2.6), (r"onde (esta|anda|ta) (o )?meu pedido", 2.6),
                         (r"status (do|de entrega|da entrega)", 2.0), (r"rastreio|rastreamento|codigo de rastreio", 1.6),
                         (r"ja saiu (pra|para) entrega", 2.0), (r"nao chegou ainda|ainda nao chegou", 1.6),
                         (r"(nenhuma|sem) (informacao|atualizacao)", 1.4), (r"saber (o status|onde esta)", 1.8)],
    "cancelamento": [(r"cancel(ar|em|amento)", 2.6), (r"desistir da compra", 2.0)],
    "status_reembolso": [(r"estorn", 2.8), (r"reembols", 2.6), (r"nao caiu", 1.4), (r"credit(ado|o)", 1.0),
                         (r"cancelei", 1.4)],
    "troca_devolucao": [(r"\btroc(ar|a)\b", 2.2), (r"devolv(er|o)|devolucao", 2.4), (r"outra cor|outro tamanho", 1.2)],
    "duvida_produto": [(r"quantas horas", 2.0), (r"(da|consigo|posso) (pra |para )?personalizar", 2.0),
                       (r"prazo de producao", 2.2), (r"\bcabe\b", 1.6), (r"lava.?loucas", 2.0), (r"fazem (capinha|copo|garrafa)", 2.0),
                       (r"gostaria de saber se", 1.0), (r"mantem (gelado|quente)", 2.0)],
    "elogio": [(r"\bamei\b", 2.4), (r"parabens", 2.0), (r"agradec", 1.8), (r"elogi", 2.2), (r"veio perfeito", 2.0),
               (r"antes do prazo", 1.2)],
}
# Intenções de ação explícita prevalecem sobre a queixa que as motivou ("quero cancelar, demorou demais").
_PRECEDENCE = {"cancelamento": 1.0, "status_reembolso": 0.8, "nao_recebido": 0.8, "produto_errado": 0.6}

_REPEAT_HINTS = [r"(ja e|e) a \d+.? vez", r"de novo", r"novamente", r"mandei mensagem ha", r"ja entrei em contato",
                 r"varios contatos", r"continuo sem (solucao|resposta)", r"sem solucao apos"]
_LEGAL = [r"procon", r"advogad", r"justica", r"processar", r"meus direitos", r"juizado", r"reclame aqui"]
_NEG = [r"absurd", r"pessim", r"descaso", r"vergonha", r"nunca mais", r"palhacada", r"ridicul", r"lament", r"revoltad",
        r"ninguem (responde|resolve|me avisa)", r"sem resposta", r"exijo", r"quero meu dinheiro"]
_POS = [r"\bamei\b", r"parabens", r"obrigad", r"perfeit", r"adorei", r"excelente", r"agradec"]
_ORDER_RE = re.compile(r"(?:#|pedido\s*(?:n[ºo°.]?\s*)?|ordem\s*)(\d{4,12})", re.I)
_PII_RES = [(re.compile(r"\(?\b\d{2}\)?\s?9?\d{4}-?\d{4}\b"), "[telefone]"),
            (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[e-mail]"),
            (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "[cpf]")]


def mask_pii(text: Optional[str]) -> str:
    """Mascara telefone, e-mail e CPF em textos exibidos ou enviados a modelos (minimização de dados)."""
    t = str(text or "")
    for rx, repl in _PII_RES:
        t = rx.sub(repl, t)
    return t


def _any(patterns: List[str], text: str) -> List[str]:
    return [p for p in patterns if re.search(p, text)]


def classify_intent(subject: Optional[str], message: str) -> Dict[str, Any]:
    text = normalize(f"{subject or ''} {message or ''}")
    scores: Dict[str, float] = {}
    matched: Dict[str, List[str]] = {}
    for intent, rules in INTENT_RULES.items():
        hits = [(p, w) for p, w in rules if re.search(p, text)]
        if hits:
            scores[intent] = sum(w for _, w in hits) + (_PRECEDENCE.get(intent, 0) if hits else 0)
            matched[intent] = [p for p, _ in hits]
    if "nao_recebido" in scores and "onde_esta_pedido" in scores:
        scores["onde_esta_pedido"] -= 1.5   # "consta entregue e não chegou" não é dúvida de status
    if "status_reembolso" in scores and "cancelamento" in scores and re.search(r"cancelei|solicitei o cancelamento", text):
        scores["cancelamento"] -= 2.0       # já cancelou: pergunta é sobre o estorno
    if not scores:
        return {"intent": "outros", "confidence": 0.3, "matched": [], "alternatives": []}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top, top_s = ranked[0]
    second_s = ranked[1][1] if len(ranked) > 1 else 0.0
    confidence = max(0.35, min(0.98, 0.5 + (top_s - max(second_s, 0)) / (top_s + 2.5) * 0.6 + min(top_s, 5) * 0.04))
    return {"intent": top, "confidence": round(confidence, 2), "matched": matched.get(top, []),
            "alternatives": [{"intent": k, "score": round(v, 2)} for k, v in ranked[1:3]]}


def is_repeat_text(subject: Optional[str], message: str) -> bool:
    return bool(_any(_REPEAT_HINTS, normalize(f"{subject or ''} {message or ''}")))


def sentiment(subject: Optional[str], message: str) -> Dict[str, Any]:
    raw = f"{subject or ''} {message or ''}"
    text = normalize(raw)
    neg, pos, legal = _any(_NEG, text), _any(_POS, text), _any(_LEGAL, text)
    caps = sum(1 for w in re.findall(r"\b[A-ZÁÉÍÓÚÃÕÇ]{3,}\b", raw)) >= 1
    shout = raw.count("!") >= 2 or "😡" in raw
    score = len(pos) - len(neg) * 1.2 - (1 if caps or shout else 0) - len(legal) * 1.5
    label = ("muito_negativo" if score <= -2.5 or legal else "negativo" if score < -0.4 else
             "positivo" if score > 0.6 else "neutro")
    return {"label": label, "legal_threat": bool(legal), "signals": [*neg, *legal][:6]}


def find_order_reference(subject: Optional[str], message: str) -> Optional[str]:
    m = _ORDER_RE.search(f"{subject or ''} {message or ''}")
    return m.group(1) if m else None


def urgency(*, intent: str, channel: str, sent: Dict[str, Any], contact_number: int, delay_days: Optional[float],
            order_total: Optional[float]) -> Dict[str, Any]:
    """Urgência explicável: cada fator soma pontos; a soma vira baixa/média/alta/crítica e a prioridade (0–100)."""
    pts, why = 0, []
    if channel == "reclameaqui":
        pts += 3; why.append("Reclame Aqui (canal público, impacta reputação)")
    if sent.get("legal_threat"):
        pts += 4; why.append("Menção a Procon/Justiça/direitos")
    if sent["label"] == "muito_negativo":
        pts += 2; why.append("Sentimento muito negativo")
    elif sent["label"] == "negativo":
        pts += 1; why.append("Sentimento negativo")
    if contact_number >= 3:
        pts += 3; why.append(f"{contact_number}º contato sobre o mesmo assunto")
    elif contact_number == 2:
        pts += 2; why.append("Recontato (2º contato sobre o mesmo assunto)")
    if delay_days and delay_days >= 7:
        pts += 2; why.append(f"Atraso de {delay_days:.0f} dias")
    elif delay_days and delay_days > 0:
        pts += 1; why.append(f"Atraso de {delay_days:.0f} dia(s)")
    if INTENTS.get(intent, {}).get("claim") and intent != "atraso_entrega":
        pts += 1; why.append("Reclamação que pede reparação")
    if order_total and order_total >= 300:
        pts += 1; why.append(f"Pedido de valor alto (R$ {order_total:,.2f})".replace(",", "X").replace(".", ",").replace("X", "."))
    if intent in ("elogio", "duvida_produto"):
        pts = max(0, pts - 2)
    level = "critica" if pts >= 7 else "alta" if pts >= 4 else "media" if pts >= 2 else "baixa"
    return {"level": level, "priority": min(100, pts * 11 + (5 if level != "baixa" else 0)), "factors": why}


def injection(subject: Optional[str], message: str) -> bool:
    return injection_suspected(f"{subject or ''} {message or ''}")
