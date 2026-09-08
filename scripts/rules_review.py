"""
Review gate for the rule store. A record is written by scripts/rules_ingest.py
as status "unconfirmed" and is ignored by the scheduler and by lookup_rule
until a person has read it against its source and confirmed it here.

    python scripts/rules_review.py --list
    python scripts/rules_review.py --show site-sop
    python scripts/rules_review.py --confirm site-sop --by "M. Rasin"
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.agent import rule_store


def _show(rule_id: str, base: pathlib.Path) -> None:
    rec = rule_store.load(rule_id, base)
    text = rule_store.source_path(rec).read_text()
    print(f"# {rec.rule_id} v{rec.version}  [{rec.status}]")
    print(f"  {rec.title} - {rec.jurisdiction}")
    print(f"  source: {rec.source.path}")
    print(f"  extracted by: {rec.extraction.model} "
          f"({rec.extraction.prompt_version}) at {rec.extraction.at_utc}")
    print()
    for field, cit in rule_store._iter_citations(rec):
        a, b = cit.span
        print(f"  {field}")
        print(f"    span [{a}:{b}]  {text[a:b]!r}")
    problems = rule_store.check_citations(rec, text)
    print()
    print("  citations OK" if not problems else f"  PROBLEMS: {problems}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=pathlib.Path, default=rule_store.RULES_DIR)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--show")
    ap.add_argument("--confirm")
    ap.add_argument("--by", help="reviewer name, required with --confirm")
    args = ap.parse_args()

    if args.list:
        for rid in rule_store.list_ids(args.base):
            rec = rule_store.load(rid, args.base)
            print(f"{rec.status:>11}  {rid}  v{rec.version}  "
                  f"(reviewed by {rec.review.by or '-'})")
        return

    if args.show:
        _show(args.show, args.base)
        return

    if args.confirm:
        if not args.by:
            ap.error("--confirm requires --by")
        rec = rule_store.load(args.confirm, args.base)
        text = rule_store.source_path(rec).read_text()
        problems = rule_store.check_citations(rec, text)
        if problems:
            raise SystemExit(f"refusing to confirm {args.confirm}: {problems}")
        rec.status = "confirmed"
        rec.review.by = args.by
        rec.review.at = dt.datetime.now(dt.timezone.utc)
        (args.base / f"{rec.rule_id}.json").write_text(
            rec.model_dump_json(indent=2))
        print(f"confirmed {rec.rule_id} v{rec.version} by {args.by}")
        return

    ap.error("nothing to do; use --list, --show or --confirm")


if __name__ == "__main__":
    main()
