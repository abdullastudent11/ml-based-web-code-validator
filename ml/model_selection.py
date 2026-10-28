"""Choose simple classifier settings using only the validation split."""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from .model import NaiveBayesErrorClassifier


ALPHA_CANDIDATES = (0.25, 0.5, 1.0, 2.0)
FEATURE_CANDIDATES = ("token_parser", "token_char_parser")


def _macro_f1(records: list[tuple[str, str]]) -> float:
    labels = sorted({label for pair in records for label in pair})
    if not labels:
        return 0.0
    confusion = {label: Counter() for label in labels}
    for actual, predicted in records:
        confusion[actual][predicted] += 1
    scores = []
    for label in labels:
        true_positive = confusion[label][label]
        false_positive = sum(
            confusion[other][label] for other in labels if other != label
        )
        false_negative = sum(
            confusion[label][other] for other in labels if other != label
        )
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return sum(scores) / len(scores)


def select_model_configuration(
    training_examples: Iterable[dict[str, object]],
    validation_examples: Iterable[dict[str, object]],
) -> dict[str, object]:
    """Select alpha and feature mode from grouped validation examples only."""
    training = list(training_examples)
    validation = list(validation_examples)
    if not training or not validation:
        raise ValueError("model selection requires non-empty train and validation splits")

    candidates: list[dict[str, object]] = []
    for feature_mode in FEATURE_CANDIDATES:
        for alpha in ALPHA_CANDIDATES:
            classifier = NaiveBayesErrorClassifier.fit(
                training, alpha=alpha, feature_mode=feature_mode
            )
            records: list[tuple[str, str]] = []
            for example in validation:
                language = str(example["language"])
                actual = str(example["label"])
                predicted = str(
                    classifier.predict(language, str(example["source"]), top_k=1)[0][
                        "category"
                    ]
                )
                records.append((f"{language}:{actual}", f"{language}:{predicted}"))
            accuracy = sum(actual == predicted for actual, predicted in records) / len(records)
            candidates.append(
                {
                    "feature_mode": feature_mode,
                    "alpha": alpha,
                    "validation_examples": len(records),
                    "validation_accuracy": round(accuracy, 4),
                    "validation_macro_f1": round(_macro_f1(records), 4),
                }
            )

    candidates.sort(
        key=lambda candidate: (
            -float(candidate["validation_macro_f1"]),
            -float(candidate["validation_accuracy"]),
            0 if candidate["feature_mode"] == "token_char_parser" else 1,
            float(candidate["alpha"]),
        )
    )
    return {"selected": candidates[0], "candidates": candidates}
