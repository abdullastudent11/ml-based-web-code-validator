"""Unit tests for the baseline classifier and backend-facing analyzer."""

from __future__ import annotations

import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

from ml.analyzer import ErrorAnalyzer
from ml.dataset import load_examples
from ml.demo import read_source
from ml.model import NaiveBayesErrorClassifier


class ClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.examples = [
            {"language": "html", "source": "<div>hello", "label": "html_unclosed_tag"},
            {"language": "html", "source": "<section>world", "label": "html_unclosed_tag"},
            {"language": "html", "source": "<p>hello</p>", "label": "no_likely_error"},
            {"language": "html", "source": "<main>world</main>", "label": "no_likely_error"},
        ]
        self.classifier = NaiveBayesErrorClassifier.fit(self.examples)

    def test_prediction_scores_are_ranked_and_not_confirmed(self) -> None:
        predictions = self.classifier.predict("html", "<div>hello", top_k=2)
        self.assertEqual(predictions[0]["category"], "html_unclosed_tag")
        self.assertEqual(len(predictions), 2)
        self.assertTrue(all(item["is_confirmed"] is False for item in predictions))
        self.assertAlmostEqual(
            sum(float(item["confidence"]) for item in predictions), 1.0, places=5
        )

    def test_save_and_load_preserves_predictions(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parents[1]
        ) as temp_dir:
            model_path = Path(temp_dir) / "model.json"
            self.classifier.save(model_path)
            loaded = NaiveBayesErrorClassifier.load(model_path)
        self.assertEqual(
            self.classifier.predict("html", "<div>hello"),
            loaded.predict("html", "<div>hello"),
        )

    def test_empty_source_has_no_prediction(self) -> None:
        self.assertEqual(self.classifier.predict("html", "  "), [])

    def test_training_examples_are_explicitly_synthetic_and_split(self) -> None:
        examples = load_examples()
        self.assertTrue(examples)
        self.assertEqual(
            {example["origin"] for example in examples},
            {"grammar_generated_synthetic", "hand_authored_synthetic"},
        )
        self.assertEqual(
            {example["split"] for example in examples},
            {"train", "validation", "test"},
        )
        group_splits: dict[str, set[str]] = defaultdict(set)
        for example in examples:
            if example["origin"] == "grammar_generated_synthetic":
                group_splits[str(example["group_id"])].add(str(example["split"]))
        self.assertTrue(all(len(splits) == 1 for splits in group_splits.values()))

    def test_analyzer_keeps_predictions_and_diagnostics_separate(self) -> None:
        classifier = NaiveBayesErrorClassifier.fit(
            [
                {"language": "html", "source": "<div>hello", "label": "html_unclosed_tag"},
                {"language": "html", "source": "<p>hello</p>", "label": "no_likely_error"},
                {"language": "css", "source": ".a { color red; }", "label": "css_missing_colon"},
                {"language": "css", "source": ".a { color: red; }", "label": "no_likely_error"},
                {"language": "javascript", "source": "const x = [1;", "label": "javascript_unclosed_delimiter"},
                {"language": "javascript", "source": "const x = [1];", "label": "no_likely_error"},
            ]
        )
        result = ErrorAnalyzer(classifier=classifier).analyze(html="<div>hello")
        self.assertIn("predictions", result)
        self.assertIn("deterministic_diagnostics", result)
        prediction = result["predictions"]["html"][0]
        self.assertEqual(prediction["source"], "model_prediction")
        self.assertFalse(prediction["is_confirmed"])
        self.assertEqual(result["deterministic_diagnostics"]["css"]["status"], "not_provided")

    def test_saved_model_accepts_the_users_complete_html_example(self) -> None:
        source = """<!DOCTYPE html>
<html>
<head>
    <title>My Page</title>
</head>
<body>
    <h1>Welcome</h1>
    <p>This is a test page.</p>
</body>
</html>"""
        result = ErrorAnalyzer().analyze(html=source, top_k=1)
        self.assertEqual(
            result["predictions"]["html"][0]["category"], "no_likely_error"
        )
        self.assertEqual(result["deterministic_diagnostics"]["html"]["items"], [])


class ParserDiagnosticTests(unittest.TestCase):
    def test_complete_html_document_is_not_parsed_as_a_fragment(self) -> None:
        from ml.diagnostics import diagnose_source

        source = """<!DOCTYPE html>
<html>
<head>
    <title>My Page</title>
</head>
<body>
    <h1>Welcome</h1>
    <p>This is a test page.</p>
</body>
</html>"""
        result = diagnose_source("html", source)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["items"], [])

    def test_javascript_parse_error_is_separate_from_prediction(self) -> None:
        from ml.diagnostics import diagnose_source

        result = diagnose_source("javascript", "const value = ;")
        self.assertEqual(result["status"], "available")
        self.assertTrue(result["items"])
        self.assertEqual(result["items"][0]["source"], "deterministic_parser")
        self.assertFalse(result["items"][0]["is_model_prediction"])
        self.assertFalse(result["items"][0]["is_confirmed_compiler_error"])


    def test_css_parse_error_is_separate_from_prediction(self) -> None:
        from ml.diagnostics import diagnose_source

        result = diagnose_source("css", ".card { color red; }")
        self.assertEqual(result["status"], "available")
        self.assertTrue(result["items"])
        self.assertEqual(result["items"][0]["source"], "deterministic_parser")

    def test_css_unclosed_block_and_string_have_distinct_codes(self) -> None:
        from ml.diagnostics import diagnose_source

        block = diagnose_source("css", ".card { color: red;")
        string = diagnose_source("css", ".card { --note: \"open; }")
        self.assertIn("CSS_UNCLOSED_BLOCK", {item["code"] for item in block["items"]})
        self.assertIn(
            "CSS_UNTERMINATED_STRING", {item["code"] for item in string["items"]}
        )
        self.assertNotIn(
            "CSS_UNCLOSED_BLOCK", {item["code"] for item in string["items"]}
        )

    def test_javascript_errors_are_normalized_for_model_features(self) -> None:
        from ml.diagnostics import diagnose_source

        cases = {
            "const result = compute(4, 2;": "JAVASCRIPT_UNCLOSED_DELIMITER",
            "const path = 'home;": "JAVASCRIPT_UNTERMINATED_STRING",
            "const broken = ;": "JAVASCRIPT_UNEXPECTED_TOKEN",
        }
        for source, expected_code in cases.items():
            with self.subTest(source=source):
                result = diagnose_source("javascript", source)
                self.assertEqual(result["items"][0]["code"], expected_code)

    def test_html5_parser_finding_is_nonfatal_and_deterministic(self) -> None:
        from ml.diagnostics import diagnose_source

        result = diagnose_source("html", "</div>")
        self.assertEqual(result["status"], "available")
        self.assertTrue(result["items"])
        self.assertEqual(result["items"][0]["parser"], "html5lib")
        self.assertFalse(result["items"][0]["is_confirmed_compiler_error"])


class DemoTests(unittest.TestCase):
    def test_interactive_demo_reads_multiline_source_and_can_skip(self) -> None:
        lines = iter(["<main>", "  <h1>Title</h1>", "</main>", "END"])
        source = read_source(
            "html", lambda _prompt: next(lines), output_fn=lambda _message: None
        )
        self.assertEqual(source, "<main>\n  <h1>Title</h1>\n</main>")

        skip = iter(["END"])
        self.assertIsNone(
            read_source("css", lambda _prompt: next(skip), output_fn=lambda _message: None)
        )


if __name__ == "__main__":
    unittest.main()
