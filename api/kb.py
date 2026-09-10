"""
Curated heat-safety knowledge base. A dozen short entries under
`api/data/kb/`, each with a title, plain-language text, a published source,
and keyword tags. Retrieval is deterministic keyword overlap over the handful
of entries. Nothing here is computed and nothing is a number Harara relies on.

The assistant answers a heat, first-aid, acclimatisation or "what is Harara"
question by serving a retrieved entry's own text with its source shown. It does
not paraphrase entries through the model. If nothing matches, it says so and
offers the tools it does have. Text loaded here is reference data, never
instructions: an entry cannot change the assistant's behaviour.
"""

from __future__ import annotations

import json
import pathlib
import re

KB_DIR = pathlib.Path(__file__).parent / "data" / "kb"

_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "what", "whats", "how", "why",
    "does", "do", "did", "of", "in", "on", "to", "and", "or", "it", "its", "for",
    "this", "that", "these", "those", "with", "as", "at", "by", "be", "can",
    "could", "should", "would", "i", "my", "me", "we", "our", "you", "your",
    "they", "them", "if", "so", "about", "tell", "explain", "mean", "means",
}


def _load() -> list[dict]:
    out: list[dict] = []
    for p in sorted(KB_DIR.glob("*.json")):
        d = json.loads(p.read_text())
        d["id"] = p.stem
        out.append(d)
    return out


ENTRIES: list[dict] = _load()
BY_ID: dict[str, dict] = {e["id"]: e for e in ENTRIES}

# Jurisdiction rule summaries are served by the chat's rules handler, keyed by
# country, not by free-text search, so they stay out of the answer() pool where
# a bare word like "rule" would otherwise pull them in.
RULE_IDS = {"qatar-rule", "uae-midday-break", "saudi-midday-ban"}
_ANSWERABLE = [e for e in ENTRIES if e["id"] not in RULE_IDS]


_SUFFIX = re.compile(r"(?:ations?|ising|izing|isation|ization|ised|ized|ise|ize"
                     r"|ing|ers?|ed|es|s)$")


def _stem(w: str) -> str:
    return _SUFFIX.sub("", w) if len(w) > 5 else w


def _tokens(s: str) -> set[str]:
    return {_stem(w) for w in _WORD.findall((s or "").lower())
            if w not in _STOP and len(w) > 2}


def search(query: str, *, k: int = 1, min_score: int = 3,
           pool: list[dict] | None = None) -> list[dict]:
    """Best entries for a query by keyword overlap, keyword hits weighted x3.
    Empty when the best match is too weak to trust."""
    q = _tokens(query)
    if not q:
        return []
    scored: list[tuple[int, dict]] = []
    for e in (pool if pool is not None else _ANSWERABLE):
        kw = {_stem(w) for w in _WORD.findall(" ".join(e.get("keywords", [])).lower())
              if len(w) > 2}
        body = _tokens(e.get("text", "")) | _tokens(e.get("title", ""))
        score = len(q & body) + 3 * len(q & kw)
        if score:
            scored.append((score, e))
    if not scored:
        return []
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    if scored[0][0] < min_score:
        return []
    return [e for _, e in scored[:k]]


def get(entry_id: str) -> dict | None:
    return BY_ID.get(entry_id)


def answer(query: str) -> dict | None:
    """A single grounded answer: {text, source, id, title} or None."""
    hits = search(query, k=1)
    if not hits:
        return None
    e = hits[0]
    return {"id": e["id"], "title": e["title"], "text": e["text"],
            "source": e["source"]}
