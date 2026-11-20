"""Load the FP2 corpus and golden labels from data/."""

import csv
import json
from collections.abc import Iterator
from pathlib import Path

from kangaroo.config import DATA_DIR
from kangaroo.models.case import Case
from kangaroo.models.golden import GoldenLabel

CORPUS_PATH = DATA_DIR / "corpus.jsonl"
GOLDEN_PATH = DATA_DIR / "golden.csv"


def load_cases(path: Path = CORPUS_PATH) -> list[Case]:
    """Every corpus case, keeping only `id` and `content`."""
    return [Case.model_validate({"id": raw["id"], "content": raw["content"]}) for raw in _raw(path)]


def load_golden_labels(
    golden_path: Path = GOLDEN_PATH, corpus_path: Path = CORPUS_PATH
) -> list[GoldenLabel]:
    """Golden labels plus each case's action tier, for scoring only."""
    action_tiers = {raw["id"]: raw["target_tier"] for raw in _raw(corpus_path)}

    with golden_path.open(encoding="utf-8", newline="") as f:
        return [
            GoldenLabel(
                case_id=row["case_id"],
                final=row["final"],
                notes=row["notes"],
                action_tier=action_tiers[row["case_id"]],
            )
            for row in csv.DictReader(f)
        ]


def _raw(path: Path) -> Iterator[dict]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)
