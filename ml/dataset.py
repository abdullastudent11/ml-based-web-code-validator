"""Read and validate the labeled JSONL dataset used for training/evaluation."""

from __future__ import annotations

import json
from pathlib import Path

from .model import LANGUAGES


DEFAULT_DATASET_PATH = Path(__file__).parent / "data" / "grammar_examples.jsonl"
SPLITS = {"train", "validation", "test"}


def load_examples(path: str | Path = DEFAULT_DATASET_PATH) -> list[dict[str, str]]:
    examples: list[dict[str, str]] = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON on dataset line {line_number}: {error}") from error
        if not isinstance(row, dict):
            raise ValueError(f"dataset line {line_number} must be a JSON object")

        language = row.get("language")
        source = row.get("source")
        label = row.get("label")
        split = row.get("split")
        origin = row.get("origin")
        if language not in LANGUAGES:
            raise ValueError(f"unsupported language on dataset line {line_number}")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(f"empty source on dataset line {line_number}")
        if not isinstance(label, str) or not label:
            raise ValueError(f"empty label on dataset line {line_number}")
        if split not in SPLITS:
            raise ValueError(f"invalid split on dataset line {line_number}")
        if not isinstance(origin, str) or not origin:
            raise ValueError(f"missing data origin on dataset line {line_number}")
        example = {
            "language": language,
            "source": source,
            "label": label,
            "split": split,
            "origin": origin,
        }
        group_id = row.get("group_id")
        if group_id is not None:
            if not isinstance(group_id, str) or not group_id:
                raise ValueError(f"invalid group id on dataset line {line_number}")
            example["group_id"] = group_id
        examples.append(example)

    if not examples:
        raise ValueError("dataset contains no examples")
    return examples
