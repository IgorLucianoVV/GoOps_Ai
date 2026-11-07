"""NLP determinístico para comentários em português (sem LLM).

Recursos: normalização (minúsculas, remoção de acentos para comparação), tokenização,
stopwords, unigramas, bigramas, temas recorrentes (dicionário versionado), sentimento
léxico simples e detecção de tentativas de prompt injection (o texto é sempre DADO).
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Dict, Iterable, List, Optional

THEMES_VERSION = "1.0"

STOPWORDS = set("""
a à ao aos aquela aquelas aquele aqueles aquilo as às até com como da das de dela delas dele deles depois do dos
e é ela elas ele eles em entre era eram essa essas esse esses esta está estão estas este estes eu foi foram há
isso isto já lhe lhes mais mas me mesmo meu meus minha minhas muito na nas nem no nos nós num numa o os ou para
pela pelas pelo pelos por qual quando que quem se sem ser seu seus só sua suas também te tem têm tinha um uma umas
uns você vocês vos ja la so pra pro pois sobre ter tive teve estou estava sim ai aqui ali lá então tudo todo toda
todos todas cada qualquer outro outra outros outras
""".split())
# "não" e "nunca" NÃO são stopwords: carregam significado ("não chegou", "nunca mais").
STOPWORDS -= {"não", "nunca"}

THEMES: Dict[str, Dict[str, object]] = {
    "entrega_atrasada": {"label": "Entrega atrasada", "polarity": "negative",
                         "patterns": [r"atras", r"demor", r"nao chegou", r"prazo"]},
    "produto_danificado": {"label": "Produto quebrado/defeituoso", "polarity": "negative",
                           "patterns": [r"quebr", r"danific", r"defeito", r"vaza", r"vazando", r"riscad"]},
    "pedido_incompleto": {"label": "Pedido incompleto", "polarity": "negative",
                          "patterns": [r"incomplet", r"faltou", r"faltando"]},
    "atendimento_negativo": {"label": "Atendimento insatisfatório", "polarity": "negative",
                             "patterns": [r"pessimo atendimento", r"atendimento pessimo", r"sem resposta", r"ninguem (me )?(avisou|respond)"]},
    "atendimento_excelente": {"label": "Atendimento excelente", "polarity": "positive",
                              "patterns": [r"atendimento (excelente|otimo|bom)"]},
    "entrega_rapida": {"label": "Entrega rápida", "polarity": "positive",
                       "patterns": [r"chegou rapido", r"entrega rapida", r"antes do prazo"]},
    "qualidade_positiva": {"label": "Qualidade elogiada", "polarity": "positive",
                           "patterns": [r"qualidade (otima|excelente|boa)", r"lindo", r"perfeito", r"amei", r"superou"]},
}

_INJECTION_PATTERNS = [r"ignore (as|todas as)? ?instruc", r"ignore previous", r"system prompt", r"aprove todos",
                       r"voce agora e", r"disregard"]
_POS = {"excelente", "otimo", "otima", "lindo", "perfeito", "amei", "recomendo", "rapido", "rapida", "bom", "boa", "superou"}
_NEG = {"atrasada", "atrasou", "atraso", "quebrado", "defeito", "vazando", "pessimo", "demorou", "incompleto",
        "faltou", "nunca", "ruim", "riscado"}


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def normalize(text: Optional[str]) -> str:
    if not text:
        return ""
    t = strip_accents(str(text).lower())
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_STOP_NORM = {strip_accents(w) for w in STOPWORDS}


def tokenize(text: Optional[str]) -> List[str]:
    return [t for t in normalize(text).split() if len(t) > 1 and t not in _STOP_NORM and not t.isdigit()]


def bigrams(tokens: List[str]) -> List[str]:
    return [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]


def detect_themes(text: Optional[str]) -> List[str]:
    norm = normalize(text)
    if not norm:
        return []
    return [key for key, spec in THEMES.items() if any(re.search(p, norm) for p in spec["patterns"])]


def sentiment(text: Optional[str]) -> Optional[str]:
    toks = normalize(text).split()
    if not toks:
        return None
    score = sum(t in _POS for t in toks) - sum(t in _NEG for t in toks)
    return "positive" if score > 0 else ("negative" if score < 0 else "neutral")


def injection_suspected(text: Optional[str]) -> bool:
    norm = normalize(text)
    return any(re.search(p, norm) for p in _INJECTION_PATTERNS)


def frequencies(texts: Iterable[Optional[str]], top: int = 20) -> Dict[str, object]:
    texts = [t for t in texts if t and str(t).strip()]
    uni: Counter = Counter()
    bi: Counter = Counter()
    themes: Counter = Counter()
    for t in texts:
        toks = tokenize(t)
        uni.update(toks)
        bi.update(bigrams(toks))
        themes.update(detect_themes(t))
    return {
        "comments_processed": len(texts),
        "unigrams": [{"term": k, "count": v} for k, v in uni.most_common(top)],
        "bigrams": [{"term": k, "count": v} for k, v in bi.most_common(top)],
        "themes": [{"theme": k, "label": THEMES[k]["label"], "polarity": THEMES[k]["polarity"], "count": v,
                    "share": round(v / len(texts), 4) if texts else None} for k, v in themes.most_common()],
    }
