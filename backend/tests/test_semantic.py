"""Focused checks for conservative semantic validation."""

from __future__ import annotations

import unittest

from backend.javascript_semantic import validate_javascript_semantics
from backend.semantic import validate_css_semantics, validate_html_semantics


class HtmlSemanticTests(unittest.TestCase):
    def test_reports_duplicate_ids_and_unresolved_references(self) -> None:
        source = """<label for="missing">Email</label>
<img src="avatar.png">
<a href="#nowhere">Go</a>
<p id="same"></p><p id="same"></p>
<div aria-labelledby="missing-title"></div>"""
        result = validate_html_semantics(source)
        self.assertEqual(result["status"], "available")
        self.assertEqual(
            {item["code"] for item in result["items"]},
            {
                "HTML_LABEL_TARGET_NOT_FOUND",
                "HTML_IMAGE_MISSING_ALT",
                "HTML_FRAGMENT_TARGET_NOT_FOUND",
                "HTML_DUPLICATE_ID",
                "HTML_ARIA_REFERENCE_NOT_FOUND",
            },
        )

    def test_valid_references_and_decorative_image_are_clean(self) -> None:
        source = """<label for="email">Email</label>
<input id="email">
<img src="divider.svg" alt="">
<a href="#details">Details</a>
<h2 id="details">Details</h2>
<p id="title">Information</p><section aria-labelledby="title"></section>"""
        self.assertEqual(validate_html_semantics(source)["items"], [])


class CssSemanticTests(unittest.TestCase):
    def test_reports_undefined_custom_property_but_accepts_fallback(self) -> None:
        source = """:root { --brand: teal; }
.card { color: var(--missing); border-color: var(--optional, blue); outline-color: var(--brand); }"""
        result = validate_css_semantics(source)
        self.assertEqual(
            [item["code"] for item in result["items"]],
            ["CSS_UNDEFINED_CUSTOM_PROPERTY"],
        )
        self.assertIn('"--missing"', result["items"][0]["message"])

    def test_empty_and_missing_source_statuses(self) -> None:
        self.assertEqual(validate_css_semantics(None)["status"], "not_provided")
        self.assertEqual(validate_css_semantics(" \n ")["status"], "empty")


class JavaScriptSemanticTests(unittest.TestCase):
    def test_reports_undeclared_identifier(self) -> None:
        result = validate_javascript_semantics("console.log(missingName);")
        self.assertEqual(
            [item["code"] for item in result["items"]],
            ["JAVASCRIPT_UNDECLARED_IDENTIFIER"],
        )
        self.assertIn('"missingName"', result["items"][0]["message"])

    def test_resolves_parameters_locals_globals_and_property_names(self) -> None:
        source = """const user = { name: "A" };
function greet(person) {
  const text = person.name;
  console.log(text, user.name);
}
greet(user);"""
        result = validate_javascript_semantics(source)
        self.assertEqual(result["items"], [])

    def test_resolves_arrow_parameters_and_destructuring(self) -> None:
        result = validate_javascript_semantics(
            "const { value } = inputData; const plusOne = (count) => count + value;"
        )
        self.assertEqual(
            [item["message"] for item in result["items"]],
            ['Identifier "inputData" is not declared in this source or in the known browser/Node.js globals.'],
        )

    def test_skips_semantics_when_parser_has_reported_syntax_error(self) -> None:
        result = validate_javascript_semantics(
            "const answer = ;",
            parser_findings=[{"code": "JAVASCRIPT_UNEXPECTED_TOKEN"}],
        )
        self.assertEqual(result["status"], "skipped_syntax_error")
        self.assertEqual(result["items"], [])

    def test_does_not_report_block_local_bindings_as_global(self) -> None:
        source = """if (true) { const localValue = 3; console.log(localValue); }
console.log(window.location.href);"""
        self.assertEqual(validate_javascript_semantics(source)["items"], [])


if __name__ == "__main__":
    unittest.main()
