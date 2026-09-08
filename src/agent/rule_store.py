"""
Versioned rule store under data/rules/. Each rule is a JSON record
(schemas.RuleRecord) with a source text file under data/rules/sources/.

Every constraint value carries a Citation whose character span must match
the quoted text exactly; load() and save() both enforce this. A record
enters as status "unconfirmed" and is not returned to the scheduler until
scripts/rules_review.py confirms it.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Iterable

from src.agent.schemas import Citation, RuleRecord

RULES_DIR = pathlib.Path("data/rules")
SOURCES_DIR = RULES_DIR / "sources"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _iter_citations(rec: RuleRecord) -> Iterable[tuple[str, Citation]]:
    c = rec.constraints
    for i, w in enumerate(c.banned_hour_windows):
        yield f"banned_hour_windows[{i}]", w.citation
    if c.wbgt_stop_work_c:
        yield "wbgt_stop_work_c", c.wbgt_stop_work_c.citation
    if c.seasonal_window:
        yield "seasonal_window", c.seasonal_window.citation
    for i, r in enumerate(c.workload_rest_ratios):
        yield f"workload_rest_ratios[{i}]", r.citation


def check_citations(rec: RuleRecord, source_text: str) -> list[str]:
    """Return a list of problems; empty means every span matches its quote."""
    problems = []
    n = len(source_text)
    for field, cit in _iter_citations(rec):
        a, b = cit.span
        if not (0 <= a < b <= n):
            problems.append(f"{field}: span {cit.span} out of range 0..{n}")
            continue
        if source_text[a:b] != cit.quote:
            problems.append(
                f"{field}: source[{a}:{b}]={source_text[a:b]!r} != "
                f"quote={cit.quote!r}")
    return problems


def source_path(rec: RuleRecord) -> pathlib.Path:
    return pathlib.Path(rec.source.path)


def load(rule_id: str, base: pathlib.Path = RULES_DIR) -> RuleRecord:
    p = base / f"{rule_id}.json"
    if not p.exists():
        raise FileNotFoundError(p)
    rec = RuleRecord.model_validate_json(p.read_text())
    src = pathlib.Path(rec.source.path)
    if src.exists():
        text = src.read_text()
        if rec.source.sha256 and sha256_text(text) != rec.source.sha256:
            raise ValueError(f"{rule_id}: source sha256 mismatch")
        problems = check_citations(rec, text)
        if problems:
            raise ValueError(f"{rule_id}: citation check failed: {problems}")
    return rec


def list_ids(base: pathlib.Path = RULES_DIR) -> list[str]:
    return sorted(p.stem for p in base.glob("*.json"))


def load_all(base: pathlib.Path = RULES_DIR) -> list[RuleRecord]:
    return [load(i, base) for i in list_ids(base)]


def save(rec: RuleRecord, source_text: str,
         base: pathlib.Path = RULES_DIR) -> pathlib.Path:
    problems = check_citations(rec, source_text)
    if problems:
        raise ValueError(f"refusing to save {rec.rule_id}: {problems}")
    base.mkdir(parents=True, exist_ok=True)
    (base / "sources").mkdir(parents=True, exist_ok=True)
    src = pathlib.Path(rec.source.path)
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(source_text)
    rec.source.sha256 = sha256_text(source_text)
    p = base / f"{rec.rule_id}.json"
    p.write_text(rec.model_dump_json(indent=2))
    return p


def next_version(rule_id: str, base: pathlib.Path = RULES_DIR) -> int:
    p = base / f"{rule_id}.json"
    if not p.exists():
        return 1
    return RuleRecord.model_validate_json(p.read_text()).version + 1
