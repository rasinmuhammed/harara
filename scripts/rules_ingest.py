"""
Ingest a rule document into the versioned rule store (data/rules/).

The language model only extracts structured constraints and cites the span
of source text each one came from; src.agent.rule_store.save refuses any
record whose citations do not resolve. The record lands as status
"unconfirmed" and is invisible to the scheduler until a human runs
scripts/rules_review.py.

Single document:

    python scripts/rules_ingest.py \
        --source eval/agent_eval/rules/site-sop.txt \
        --rule-id site-sop --title "Site SOP" --jurisdiction "site policy"

Whole eval set (uses eval/agent_eval/rules/manifest.json):

    python scripts/rules_ingest.py --eval-set --out data/rules
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.agent import rule_store
from src.agent.llm import get_llm
from src.agent.schemas import (
    RuleExtractionMeta, RuleRecord, RuleReview, RuleSource,
)

PROMPT_VERSION = "rules-extract-v1"
EVAL_RULES_DIR = pathlib.Path("eval/agent_eval/rules")


def ingest_one(
    source_path: pathlib.Path,
    *,
    rule_id: str,
    title: str,
    jurisdiction: str,
    tags: list[str],
    model: str,
    out_dir: pathlib.Path,
    note: str | None = None,
) -> pathlib.Path:
    text = source_path.read_text()
    llm = get_llm(model)
    constraints = llm.extract_rule(text)
    now = dt.datetime.now(dt.timezone.utc)

    stored_source = out_dir / "sources" / f"{rule_id}{source_path.suffix}"
    rec = RuleRecord(
        rule_id=rule_id,
        version=rule_store.next_version(rule_id, out_dir),
        title=title,
        jurisdiction=jurisdiction,
        tags=tags,
        source=RuleSource(
            type="pdf" if source_path.suffix.lower() == ".pdf" else "text",
            path=str(stored_source),
            sha256="",
            retrieved_utc=now,
            note=note,
        ),
        status="unconfirmed",
        review=RuleReview(),
        extraction=RuleExtractionMeta(
            model=llm.name, prompt_version=PROMPT_VERSION, at_utc=now),
        constraints=constraints,
    )
    path = rule_store.save(rec, text, out_dir)
    return path


def _load_manifest() -> dict:
    return json.loads((EVAL_RULES_DIR / "manifest.json").read_text())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="mock",
                    help="LLM adapter name (default: mock)")
    ap.add_argument("--out", type=pathlib.Path, default=rule_store.RULES_DIR,
                    help="rule store directory (default: data/rules)")
    ap.add_argument("--eval-set", action="store_true",
                    help="ingest every document in the eval manifest")
    ap.add_argument("--source", type=pathlib.Path)
    ap.add_argument("--rule-id")
    ap.add_argument("--title")
    ap.add_argument("--jurisdiction")
    ap.add_argument("--tags", nargs="*", default=[])
    ap.add_argument("--note")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    if args.eval_set:
        manifest = _load_manifest()
        for stem, meta in manifest.items():
            path = ingest_one(
                EVAL_RULES_DIR / f"{stem}.txt",
                rule_id=meta["rule_id"], title=meta["title"],
                jurisdiction=meta["jurisdiction"], tags=meta["tags"],
                model=args.model, out_dir=args.out,
                note="synthetic eval document")
            rec = rule_store.load(meta["rule_id"], args.out)
            print(f"{path}  v{rec.version}  status={rec.status}  "
                  f"banned={len(rec.constraints.banned_hour_windows)}  "
                  f"stop={rec.constraints.wbgt_stop_work_c is not None}  "
                  f"season={rec.constraints.seasonal_window is not None}  "
                  f"ratios={len(rec.constraints.workload_rest_ratios)}")
        return

    missing = [n for n in ("source", "rule_id", "title", "jurisdiction")
               if getattr(args, n) is None]
    if missing:
        ap.error(f"single-document mode needs --{', --'.join(missing)}")

    path = ingest_one(
        args.source, rule_id=args.rule_id, title=args.title,
        jurisdiction=args.jurisdiction, tags=args.tags, model=args.model,
        out_dir=args.out, note=args.note)
    rec = rule_store.load(args.rule_id, args.out)
    print(f"{path}  v{rec.version}  status={rec.status}")


if __name__ == "__main__":
    main()
