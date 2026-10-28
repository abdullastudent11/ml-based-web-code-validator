"""Backend-friendly source analysis API for HTML, CSS, and JavaScript."""

from __future__ import annotations

from pathlib import Path

from .diagnostics import diagnose_source
from .model import NaiveBayesErrorClassifier


DEFAULT_MODEL_PATH = Path(__file__).parent / "artifacts" / "error_classifier.json"
SOURCE_FIELDS = {
    "html": "html",
    "css": "css",
    "javascript": "javascript",
}


class ErrorAnalyzer:
    """Load the trained model once and analyze source bundles on demand."""

    def __init__(
        self,
        model_path: str | Path = DEFAULT_MODEL_PATH,
        *,
        classifier: NaiveBayesErrorClassifier | None = None,
    ) -> None:
        self.classifier = classifier or NaiveBayesErrorClassifier.load(model_path)

    def analyze(
        self,
        *,
        html: str | None = None,
        css: str | None = None,
        javascript: str | None = None,
        top_k: int = 3,
    ) -> dict[str, object]:
        """Return model predictions and deterministic parser findings separately."""
        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")

        sources = {"html": html, "css": css, "javascript": javascript}
        predictions: dict[str, list[dict[str, object]]] = {}
        diagnostics: dict[str, dict[str, object]] = {}

        for language, source in sources.items():
            if source is not None and not isinstance(source, str):
                raise ValueError(f"{language} source must be a string or None")
            language_diagnostics = diagnose_source(language, source)
            diagnostics[language] = language_diagnostics
            predictions[language] = (
                self.classifier.predict(
                    language,
                    source,
                    top_k=top_k,
                    parser_diagnostics=language_diagnostics,
                )
                if source is not None and source.strip()
                else []
            )

        return {
            "model": {
                "algorithm": self.classifier.algorithm,
                "feature_mode": self.classifier.feature_mode,
                "confidence_note": (
                    "Smoothed Naive Bayes scores are not calibrated probabilities. "
                    "Predictions are not confirmed compiler errors."
                ),
            },
            "predictions": predictions,
            "deterministic_diagnostics": diagnostics,
        }


def analyze_sources(
    *,
    html: str | None = None,
    css: str | None = None,
    javascript: str | None = None,
    top_k: int = 3,
    model_path: str | Path = DEFAULT_MODEL_PATH,
) -> dict[str, object]:
    """Convenience function for a backend that does not keep an analyzer alive."""
    return ErrorAnalyzer(model_path).analyze(
        html=html, css=css, javascript=javascript, top_k=top_k
    )
