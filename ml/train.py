"""Train and save the transparent Naive Bayes source-error baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .analyzer import DEFAULT_MODEL_PATH
from .dataset import DEFAULT_DATASET_PATH, load_examples
from .model import NaiveBayesErrorClassifier
from .model_selection import select_model_configuration


def train_model(
    dataset_path: str | Path = DEFAULT_DATASET_PATH,
    model_path: str | Path = DEFAULT_MODEL_PATH,
) -> dict[str, object]:
    raw_dataset = Path(dataset_path).read_bytes()
    examples = load_examples(dataset_path)
    train_examples = [example for example in examples if example["split"] == "train"]
    validation_examples = [
        example for example in examples if example["split"] == "validation"
    ]
    if not train_examples or not validation_examples:
        raise ValueError("dataset requires non-empty train and validation splits")

    selection = select_model_configuration(train_examples, validation_examples)
    selected = selection["selected"]
    assert isinstance(selected, dict)
    final_training = train_examples + validation_examples
    classifier = NaiveBayesErrorClassifier.fit(
        final_training,
        alpha=float(selected["alpha"]),
        feature_mode=str(selected["feature_mode"]),
    )
    classifier.save(model_path)

    return {
        "model_path": str(model_path),
        "algorithm": classifier.algorithm,
        "alpha": classifier.alpha,
        "feature_mode": classifier.feature_mode,
        "training_examples": len(final_training),
        "train_examples_before_validation": len(train_examples),
        "validation_examples": len(validation_examples),
        "selected_validation_accuracy": selected["validation_accuracy"],
        "selected_validation_macro_f1": selected["validation_macro_f1"],
        "training_data_sha256": hashlib.sha256(raw_dataset).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args()
    print(json.dumps(train_model(args.dataset, args.output), indent=2))


if __name__ == "__main__":
    main()
