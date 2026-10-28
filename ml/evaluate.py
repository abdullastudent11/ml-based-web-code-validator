"""Evaluate on the fixed held-out synthetic examples and save the report."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from .dataset import DEFAULT_DATASET_PATH, load_examples
from .model import NaiveBayesErrorClassifier
from .model_selection import select_model_configuration


DEFAULT_REPORT_PATH = Path(__file__).parent / "artifacts" / "evaluation.json"


def _classification_metrics(
    records: list[tuple[str, str]], labels: list[str]
) -> dict[str, object]:
    confusion = {label: {target: 0 for target in labels} for label in labels}
    for actual, predicted in records:
        confusion[actual][predicted] += 1

    per_class: dict[str, dict[str, float | int]] = {}
    for label in labels:
        true_positive = confusion[label][label]
        false_positive = sum(confusion[other][label] for other in labels if other != label)
        false_negative = sum(confusion[label][other] for other in labels if other != label)
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0.0
        )
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = {
            "support": sum(confusion[label].values()),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    total = len(records)
    accuracy = sum(actual == predicted for actual, predicted in records) / total if total else 0.0
    return {
        "examples": total,
        "accuracy": round(accuracy, 4),
        "macro_precision": round(
            sum(float(item["precision"]) for item in per_class.values()) / len(labels), 4
        ),
        "macro_recall": round(
            sum(float(item["recall"]) for item in per_class.values()) / len(labels), 4
        ),
        "macro_f1": round(
            sum(float(item["f1"]) for item in per_class.values()) / len(labels), 4
        ),
        "per_class": per_class,
        "confusion_matrix": confusion,
    }


def evaluate_dataset(
    dataset_path: str | Path = DEFAULT_DATASET_PATH,
) -> dict[str, object]:
    raw_dataset = Path(dataset_path).read_bytes()
    examples = load_examples(dataset_path)
    train_examples = [example for example in examples if example["split"] == "train"]
    validation_examples = [
        example for example in examples if example["split"] == "validation"
    ]
    test_examples = [example for example in examples if example["split"] == "test"]
    if not train_examples or not validation_examples or not test_examples:
        raise ValueError("dataset must contain train, validation, and test examples")

    selection = select_model_configuration(train_examples, validation_examples)
    selected = selection["selected"]
    assert isinstance(selected, dict)
    final_training = train_examples + validation_examples
    classifier = NaiveBayesErrorClassifier.fit(
        final_training,
        alpha=float(selected["alpha"]),
        feature_mode=str(selected["feature_mode"]),
    )
    baseline = NaiveBayesErrorClassifier.fit(
        final_training, alpha=1.0, feature_mode="token"
    )

    def score_examples(
        model: NaiveBayesErrorClassifier,
    ) -> tuple[list[tuple[str, str]], dict[str, list[tuple[str, str]]], dict[str, list[tuple[str, str]]]]:
        overall: list[tuple[str, str]] = []
        by_language: dict[str, list[tuple[str, str]]] = {}
        by_origin: dict[str, list[tuple[str, str]]] = {}
        for example in test_examples:
            language = str(example["language"])
            actual = str(example["label"])
            origin = str(example["origin"])
            prediction = str(
                model.predict(language, str(example["source"]), top_k=1)[0]["category"]
            )
            pair = (actual, prediction)
            overall.append((f"{language}:{actual}", f"{language}:{prediction}"))
            by_language.setdefault(language, []).append(pair)
            by_origin.setdefault(origin, []).append(
                (f"{language}:{actual}", f"{language}:{prediction}")
            )
        return overall, by_language, by_origin

    overall, by_language, by_origin = score_examples(classifier)
    baseline_overall, _, _ = score_examples(baseline)

    def metrics(records: list[tuple[str, str]]) -> dict[str, object]:
        labels = sorted({label for pair in records for label in pair})
        return _classification_metrics(records, labels)

    per_language = {
        language: metrics(records)
        for language, records in sorted(by_language.items())
    }
    per_origin = {
        origin: metrics(records) for origin, records in sorted(by_origin.items())
    }
    origins = sorted({example["origin"] for example in examples})
    split_counts = Counter(example["split"] for example in examples)
    group_splits: dict[str, set[str]] = {}
    for example in examples:
        if example["origin"] == "grammar_generated_synthetic":
            group_splits.setdefault(str(example["group_id"]), set()).add(
                str(example["split"])
            )
    groups_are_disjoint = all(len(splits) == 1 for splits in group_splits.values())
    report = {
        "evaluation_data": {
            "origin": origins,
            "synthetic_only": all("synthetic" in origin for origin in origins),
            "split_counts": dict(sorted(split_counts.items())),
            "sha256": hashlib.sha256(raw_dataset).hexdigest(),
            "template_group_splits_disjoint": groups_are_disjoint,
            "holdout_note": (
                "Generated template families are kept entirely within one split. "
                "The additional hand-authored test records are kept out of training."
            ),
        },
        "model_selection": selection,
        "selected_model": {
            "algorithm": classifier.algorithm,
            "feature_mode": classifier.feature_mode,
            "alpha": classifier.alpha,
            "training_examples_including_validation": len(final_training),
        },
        "overall": metrics(overall),
        "by_language": per_language,
        "by_test_origin": per_origin,
        "reference_baseline": {
            "description": "Token-only multinomial Naive Bayes with alpha=1.0, scored on the same test split.",
            "overall": metrics(baseline_overall),
        },
        "limitations": [
            "All included examples are synthetic; these metrics do not estimate accuracy on real user code.",
            "Holding out template families reduces near-duplicate leakage but does not replace an independently collected real-world dataset.",
            "Naive Bayes confidence scores are not calibrated probabilities.",
        ],
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()
    report = evaluate_dataset(args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
