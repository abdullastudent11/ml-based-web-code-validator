"""ML error-category prediction for HTML, CSS, and JavaScript source."""

from .analyzer import ErrorAnalyzer, analyze_sources
from .model import NaiveBayesErrorClassifier

__all__ = ["ErrorAnalyzer", "NaiveBayesErrorClassifier", "analyze_sources"]
