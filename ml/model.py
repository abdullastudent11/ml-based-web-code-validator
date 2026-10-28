"""Small, transparent multinomial Naive Bayes classifier for source snippets."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from .diagnostics import diagnose_source


LANGUAGES = ("html", "css", "javascript")
FEATURE_MODES = {"token", "token_char", "token_parser", "token_char_parser"}
TOKEN_PATTERN = re.compile(
    r"</?[A-Za-z][A-Za-z0-9:-]*|[A-Za-z_$][A-Za-z0-9_$-]*|"
    r"===|!==|=>|==|!=|<=|>=|&&|\|\||\+\+|--|[^\s]"
)


def source_features(
    source: str,
    feature_mode: str = "token_char_parser",
    language: str | None = None,
    parser_diagnostics: dict[str, object] | None = None,
) -> Counter[str]:
    """Return lexical tokens and, optionally, formatting-tolerant char n-grams."""
    if feature_mode not in FEATURE_MODES:
        raise ValueError(f"unsupported feature mode: {feature_mode!r}")
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(source)]
    features: Counter[str] = Counter(f"u:{token}" for token in tokens)
    features.update(
        f"b:{left}\u241f{right}" for left, right in zip(tokens, tokens[1:])
    )
    if "char" in feature_mode:
        normalized = re.sub(r"\s+", " ", source.lower())
        character_features = {
            f"c{size}:{normalized[index : index + size]}"
            for size in (2, 3, 4)
            for index in range(max(0, len(normalized) - size + 1))
        }
        features.update({feature: 1 for feature in character_features})
    if "parser" in feature_mode:
        if language not in LANGUAGES:
            raise ValueError("parser features require a supported source language")
        if parser_diagnostics is None:
            parser_status, parser_codes = _cached_parser_features(language, source)
        else:
            parser_status = str(parser_diagnostics.get("status", "unknown"))
            parser_codes = tuple(
                str(item["code"])
                for item in parser_diagnostics.get("items", [])
                if isinstance(item, dict) and isinstance(item.get("code"), str)
            )
        features[f"p:status:{parser_status}"] = 1
        features.update({f"p:{code}": 1 for code in set(parser_codes)})
        if not parser_codes and parser_status == "available":
            features["p:no_deterministic_finding"] = 1
    return features


@lru_cache(maxsize=8192)
def _cached_parser_features(language: str, source: str) -> tuple[str, tuple[str, ...]]:
    diagnostics = diagnose_source(language, source)
    codes = tuple(
        str(item["code"])
        for item in diagnostics["items"]
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    )
    return str(diagnostics.get("status", "unknown")), codes


class NaiveBayesErrorClassifier:
    """A per-language multinomial Naive Bayes baseline.

    Confidence values are model scores from the smoothed Naive Bayes posterior;
    they are not calibrated probabilities and must not be treated as confirmed
    compiler findings. The selected model may use separate parser findings as
    input features, while the API continues to return those findings separately.
    """

    algorithm = "multinomial-naive-bayes"
    format_version = 2

    def __init__(
        self,
        *,
        alpha: float,
        classes_by_language: dict[str, dict[str, object]],
        feature_mode: str = "token_char_parser",
    ) -> None:
        if alpha <= 0:
            raise ValueError("alpha must be greater than zero")
        if feature_mode not in FEATURE_MODES:
            raise ValueError(f"unsupported feature mode: {feature_mode!r}")
        self.alpha = alpha
        self.classes_by_language = classes_by_language
        self.feature_mode = feature_mode

    @classmethod
    def fit(
        cls,
        examples: Iterable[dict[str, object]],
        alpha: float = 1.0,
        feature_mode: str = "token_char_parser",
    ) -> "NaiveBayesErrorClassifier":
        if alpha <= 0:
            raise ValueError("alpha must be greater than zero")
        if feature_mode not in FEATURE_MODES:
            raise ValueError(f"unsupported feature mode: {feature_mode!r}")

        class_documents: dict[str, Counter[str]] = defaultdict(Counter)
        class_features: dict[str, dict[str, Counter[str]]] = defaultdict(
            lambda: defaultdict(Counter)
        )
        vocabulary: dict[str, set[str]] = defaultdict(set)

        for example in examples:
            language = example.get("language")
            label = example.get("label")
            source = example.get("source")
            if language not in LANGUAGES:
                raise ValueError(f"unsupported language: {language!r}")
            if not isinstance(label, str) or not label:
                raise ValueError("each example must have a non-empty label")
            if not isinstance(source, str) or not source.strip():
                raise ValueError("each example must have non-empty source")

            features = source_features(source, feature_mode, str(language))
            class_documents[language][label] += 1
            class_features[language][label].update(features)
            vocabulary[language].update(features)

        if not class_documents:
            raise ValueError("training examples are empty")

        languages: dict[str, dict[str, object]] = {}
        for language, label_counts in sorted(class_documents.items()):
            feature_counts = class_features[language]
            languages[language] = {
                "document_counts": dict(sorted(label_counts.items())),
                "feature_counts": {
                    label: dict(sorted(counter.items()))
                    for label, counter in sorted(feature_counts.items())
                },
                "vocabulary": sorted(vocabulary[language]),
            }
        return cls(
            alpha=alpha,
            classes_by_language=languages,
            feature_mode=feature_mode,
        )

    def predict(
        self,
        language: str,
        source: str,
        top_k: int = 3,
        *,
        parser_diagnostics: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        if language not in self.classes_by_language:
            raise ValueError(f"no trained model for language {language!r}")
        if not isinstance(source, str):
            raise ValueError("source must be a string")
        if not source.strip():
            return []
        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")

        language_model = self.classes_by_language[language]
        document_counts = language_model["document_counts"]
        feature_counts = language_model["feature_counts"]
        vocabulary = language_model["vocabulary"]
        if not isinstance(document_counts, dict) or not isinstance(feature_counts, dict):
            raise ValueError("invalid classifier model data")
        if not isinstance(vocabulary, list) or not document_counts:
            raise ValueError("invalid classifier vocabulary or classes")

        class_count = len(document_counts)
        document_total = sum(int(count) for count in document_counts.values())
        feature_vector = source_features(
            source, self.feature_mode, language, parser_diagnostics
        )
        log_scores: dict[str, float] = {}

        for label, document_count in document_counts.items():
            counts = feature_counts[label]
            if not isinstance(counts, dict):
                raise ValueError("invalid classifier feature counts")
            token_total = sum(int(count) for count in counts.values())
            denominator = token_total + self.alpha * len(vocabulary)
            score = math.log(
                (int(document_count) + self.alpha)
                / (document_total + self.alpha * class_count)
            )
            for feature, frequency in feature_vector.items():
                likelihood = (int(counts.get(feature, 0)) + self.alpha) / denominator
                score += frequency * math.log(likelihood)
            log_scores[str(label)] = score

        max_score = max(log_scores.values())
        exp_scores = {
            label: math.exp(score - max_score) for label, score in log_scores.items()
        }
        score_total = sum(exp_scores.values())
        ranked = sorted(exp_scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]
        return [
            {
                "language": language,
                "category": label,
                "confidence": round(score / score_total, 6),
                "source": "model_prediction",
                "is_confirmed": False,
            }
            for label, score in ranked
        ]

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": self.format_version,
            "algorithm": self.algorithm,
            "alpha": self.alpha,
            "feature_mode": self.feature_mode,
            "classes_by_language": self.classes_by_language,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "NaiveBayesErrorClassifier":
        if payload.get("format_version") != cls.format_version:
            raise ValueError("unsupported classifier model format")
        if payload.get("algorithm") != cls.algorithm:
            raise ValueError("unsupported classifier algorithm")
        alpha = payload.get("alpha")
        feature_mode = payload.get("feature_mode", "token")
        classes = payload.get("classes_by_language")
        if (
            not isinstance(alpha, (int, float))
            or not isinstance(feature_mode, str)
            or not isinstance(classes, dict)
        ):
            raise ValueError("invalid classifier model payload")
        return cls(
            alpha=float(alpha),
            classes_by_language=classes,
            feature_mode=feature_mode,
        )

    def save(self, path: str | Path) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: str | Path) -> "NaiveBayesErrorClassifier":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("classifier model file must contain a JSON object")
        return cls.from_dict(payload)
