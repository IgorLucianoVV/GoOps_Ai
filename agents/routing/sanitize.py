"""Proteção contra prompt injection em conteúdos externos enviados a LLMs.

Conteúdo de APIs/comentários é DADO. Antes de compor prompts:
  * comentários com padrão de injeção são EXCLUÍDOS (não apenas sinalizados);
  * demais textos têm marcações de controle removidas e são truncados;
  * tudo é envolvido em <evidence> pelo chamador, e o system prompt instrui a ignorar comandos.
"""
from __future__ import annotations

import re
from typing import Iterable, List

from data_platform.analytics.nlp import injection_suspected

_CONTROL = re.compile(r"</?\s*(evidence|system|instructions?|assistant|user)\s*>", re.I)


def clean_text(text: str, max_len: int = 300) -> str:
    t = _CONTROL.sub(" ", str(text or ""))
    t = re.sub(r"[\r\n\t]+", " ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t[:max_len]


def safe_comments(comments: Iterable[str], max_items: int = 25) -> List[str]:
    out = []
    for c in comments:
        if not c or injection_suspected(c):
            continue
        out.append(clean_text(c))
        if len(out) >= max_items:
            break
    return out
