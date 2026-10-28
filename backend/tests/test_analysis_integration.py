"""The backend response joins parser, semantic, and ML results."""

from __future__ import annotations

import unittest

from backend.app import analyze_bundle, load_model_benchmark
from ml.analyzer import ErrorAnalyzer


class AnalysisIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = ErrorAnalyzer()

    def test_bundle_contains_all_three_validation_layers(self) -> None:
        result = analyze_bundle(
            self.analyzer,
            {
                "html": '<img src="logo.svg"><p id="same"></p><p id="same"></p>',
                "css": ".card { color: var(--missing); }",
                "javascript": "console.log(missingName);",
            },
            top_k=3,
        )
        self.assertEqual(
            set(result["semantic_diagnostics"]), {"html", "css", "javascript"}
        )
        self.assertIn(
            "HTML_DUPLICATE_ID",
            {item["code"] for item in result["semantic_diagnostics"]["html"]["items"]},
        )
        self.assertIn(
            "CSS_UNDEFINED_CUSTOM_PROPERTY",
            {item["code"] for item in result["semantic_diagnostics"]["css"]["items"]},
        )
        self.assertIn(
            "JAVASCRIPT_UNDECLARED_IDENTIFIER",
            {item["code"] for item in result["semantic_diagnostics"]["javascript"]["items"]},
        )
        self.assertTrue(result["predictions"]["html"])
        self.assertTrue(result["predictions"]["css"])
        self.assertTrue(result["predictions"]["javascript"])
        self.assertEqual(result["model"]["benchmark"]["dataset"], "synthetic_holdout")

    def test_invalid_javascript_skips_identifier_semantics(self) -> None:
        result = analyze_bundle(
            self.analyzer,
            {"html": None, "css": None, "javascript": "const value = ;"},
            top_k=1,
        )
        semantic = result["semantic_diagnostics"]["javascript"]
        self.assertEqual(semantic["status"], "skipped_syntax_error")
        self.assertEqual(semantic["items"], [])
        self.assertTrue(result["deterministic_diagnostics"]["javascript"]["items"])

    def test_model_benchmark_comes_from_saved_evaluation_artifact(self) -> None:
        benchmark = load_model_benchmark()
        self.assertEqual(benchmark["status"], "available")
        self.assertEqual(benchmark["test_examples"], 459)
        self.assertAlmostEqual(benchmark["accuracy"], 0.9325)
        self.assertAlmostEqual(benchmark["macro_f1"], 0.9353)


if __name__ == "__main__":
    unittest.main()
