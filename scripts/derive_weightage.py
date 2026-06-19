"""
Derive empirical GA topic weightage for an exam from its previous-year GA papers
(PYQs) and write it back into the exam's taxonomy.

This implements the "scrape PYQs → tally topic frequencies → derive empirical
weightage → feed into the per-exam prompt" flow (#7). Each PYQ is bucketed into
one of the exam's summary topics using the same hot-subtopic keywords already
declared in the taxonomy, then weights and the prompt_profile topic_distribution
are recomputed proportionally to the configured total question count.

Input PYQs (any of):
  data/questions/pyq/<exam-slug>/*.json   — list of {"question","options",...}
  data/questions/all_ga.json              — used as PYQ source for rbi-grade-b

Usage:
  python scripts/derive_weightage.py --exam upsc-banking
  python scripts/derive_weightage.py --exam rbi-grade-b --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import DEFAULT_EXAM, EXAMS  # noqa: E402


def _pyq_sources(exam: str) -> list[Path]:
    paths: list[Path] = []
    pyq_dir = BASE_DIR / "data" / "questions" / "pyq" / exam
    if pyq_dir.exists():
        paths.extend(sorted(pyq_dir.glob("*.json")))
    if exam == "rbi-grade-b":
        legacy = BASE_DIR / "data" / "questions" / "all_ga.json"
        if legacy.exists():
            paths.append(legacy)
    return paths


def _load_pyqs(exam: str) -> list[dict]:
    items: list[dict] = []
    for path in _pyq_sources(exam):
        try:
            data = json.loads(path.read_text())
        except Exception as e:  # noqa: BLE001
            print(f"  [WARN] could not read {path}: {e}")
            continue
        if isinstance(data, dict):
            data = data.get("questions") or data.get("items") or []
        if isinstance(data, list):
            items.extend(q for q in data if isinstance(q, dict))
    return items


def _q_text(q: dict) -> str:
    parts = [str(q.get("question", ""))]
    parts.extend(str(o) for o in q.get("options", []) or [])
    return " ".join(parts).lower()


def _topic_buckets(taxonomy: dict) -> dict[str, list[str]]:
    """Map each summary-section label to its keyword bag (from hot_subtopics)."""
    profile = taxonomy["prompt_profile"]
    sections = profile["summary_sections"]
    weights = taxonomy["topic_weights"]

    # Pair sections with topic_weight buckets by order (they are authored aligned).
    buckets: dict[str, list[str]] = {}
    weight_items = list(weights.values())
    for i, section in enumerate(sections):
        kws: list[str] = []
        if i < len(weight_items):
            data = weight_items[i]
            kws.append(section.lower())
            for sub in data.get("hot_subtopics", []):
                kws.extend(re.findall(r"[a-zA-Z]{4,}", sub.lower()))
        buckets[section] = sorted(set(kws))
    return buckets


def _classify(text: str, buckets: dict[str, list[str]]) -> str | None:
    best, best_hits = None, 0
    for section, kws in buckets.items():
        hits = sum(1 for k in kws if k in text)
        if hits > best_hits:
            best, best_hits = section, hits
    return best if best_hits else None


def _largest_remainder(weights: dict[str, float], total: int) -> dict[str, int]:
    raw = {k: v * total for k, v in weights.items()}
    floored = {k: int(v) for k, v in raw.items()}
    remainder = total - sum(floored.values())
    order = sorted(raw, key=lambda k: raw[k] - floored[k], reverse=True)
    for k in order[:remainder]:
        floored[k] += 1
    return floored


def derive(exam: str, dry_run: bool = False) -> None:
    cfg = EXAMS.get(exam)
    if not cfg:
        raise SystemExit(f"Unknown exam '{exam}'. Known: {', '.join(EXAMS)}")
    tax_path = BASE_DIR / cfg["taxonomy"]
    taxonomy = json.loads(tax_path.read_text())
    profile = taxonomy["prompt_profile"]
    total = profile["total_questions"]
    sections = profile["summary_sections"]

    pyqs = _load_pyqs(exam)
    if not pyqs:
        print(
            f"No PYQs found for {exam} under data/questions/pyq/{exam}/ "
            "(or data/questions/all_ga.json for rbi-grade-b). "
            "Keeping existing research-default weightage."
        )
        return

    buckets = _topic_buckets(taxonomy)
    counts = {s: 0 for s in sections}
    unclassified = 0
    for q in pyqs:
        section = _classify(_q_text(q), buckets)
        if section is None:
            unclassified += 1
            continue
        counts[section] += 1

    classified = sum(counts.values())
    print(f"Analyzed {len(pyqs)} PYQs: {classified} classified, {unclassified} unclassified.")
    if classified < max(20, len(sections) * 3):
        print("  Too few classified PYQs for a reliable distribution; not overwriting.")
        return

    shares = {s: counts[s] / classified for s in sections}
    new_dist = _largest_remainder(shares, total)

    print("Derived topic distribution:")
    for s in sections:
        print(f"  {s:<40} {counts[s]:>4} PYQs  → {new_dist[s]:>3}/{total}  ({shares[s]*100:4.1f}%)")

    if dry_run:
        print("\n(dry-run) taxonomy not modified.")
        return

    profile["topic_distribution"] = [[s, new_dist[s]] for s in sections]
    # Mirror into topic_weights percentages where buckets align by order.
    for i, data in enumerate(taxonomy["topic_weights"].values()):
        if i < len(sections):
            s = sections[i]
            data["weight_percent"] = round(shares[s] * 100, 1)
            data["questions_to_generate"] = new_dist[s]
    taxonomy.setdefault("meta", {})["weightage_source"] = (
        f"empirical:{classified}_pyqs"
    )
    tax_path.write_text(json.dumps(taxonomy, indent=2, ensure_ascii=False))
    print(f"\nUpdated {tax_path.relative_to(BASE_DIR)} with empirical weightage.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Derive GA weightage from PYQs")
    ap.add_argument("--exam", default=DEFAULT_EXAM, help="exam slug from config.EXAMS")
    ap.add_argument("--dry-run", action="store_true", help="print, do not write")
    args = ap.parse_args()
    derive(args.exam, dry_run=args.dry_run)
