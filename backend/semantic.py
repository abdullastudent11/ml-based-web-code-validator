"""Lightweight static semantic checks for HTML source."""

from __future__ import annotations

from collections import defaultdict
from html.parser import HTMLParser


class _HTMLSemanticScanner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.references: list[tuple[str, str, int, int]] = []
        self.items: list[dict[str, object]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.lower(): value or "" for name, value in attrs}
        line, offset = self.getpos()
        column = offset + 1
        element = tag.lower()

        element_id = attributes.get("id", "").strip()
        if element_id:
            self.ids[element_id].append((line, column))

        if element == "img" and "alt" not in attributes:
            self._add(
                "HTML_IMAGE_MISSING_ALT",
                "Image is missing alt text. Add alt=\"\" for a decorative image or a useful description for an informative image.",
                line,
                column,
            )

        if element == "label" and attributes.get("for", "").strip():
            self.references.append(("HTML_LABEL_TARGET_NOT_FOUND", attributes["for"].strip(), line, column))

        href = attributes.get("href", "").strip()
        if element == "a" and href.startswith("#") and len(href) > 1:
            self.references.append(("HTML_FRAGMENT_TARGET_NOT_FOUND", href[1:], line, column))

        for attribute in ("aria-labelledby", "aria-describedby"):
            for target in attributes.get(attribute, "").split():
                self.references.append(("HTML_ARIA_REFERENCE_NOT_FOUND", target, line, column))

    def _add(self, code: str, message: str, line: int, column: int) -> None:
        self.items.append(_semantic_item(code, message, line, column))


def validate_html_semantics(source: str | None) -> dict[str, object]:
    """Check a small set of useful cross-element HTML relationships."""
    if source is None:
        return {"status": "not_provided", "validator": "html_static_checks", "items": []}
    if not isinstance(source, str):
        raise ValueError("HTML source must be a string or None")
    if not source.strip():
        return {"status": "empty", "validator": "html_static_checks", "items": []}

    scanner = _HTMLSemanticScanner()
    scanner.feed(source)
    scanner.close()

    for element_id, positions in scanner.ids.items():
        for line, column in positions[1:]:
            scanner._add(
                "HTML_DUPLICATE_ID",
                f'The id "{element_id}" appears more than once in this source.',
                line,
                column,
            )

    for code, target, line, column in scanner.references:
        if target not in scanner.ids:
            if code == "HTML_LABEL_TARGET_NOT_FOUND":
                message = f'This label refers to id "{target}", but that id was not found in the source.'
            elif code == "HTML_FRAGMENT_TARGET_NOT_FOUND":
                message = f'This link points to "#{target}", but no element with that id was found in the source.'
            else:
                message = f'This accessibility reference points to id "{target}", but that id was not found in the source.'
            scanner._add(code, message, line, column)

    return {
        "status": "available",
        "validator": "html_static_checks",
        "items": scanner.items[:50],
        "note": "These static checks are advisory and do not prove browser or accessibility behavior.",
    }


def validate_css_semantics(source: str | None) -> dict[str, object]:
    """Flag CSS custom-property references without a definition or fallback."""
    if source is None:
        return {"status": "not_provided", "validator": "css_static_checks", "items": []}
    if not isinstance(source, str):
        raise ValueError("CSS source must be a string or None")
    if not source.strip():
        return {"status": "empty", "validator": "css_static_checks", "items": []}

    try:
        import tinycss2
    except ImportError:
        return {
            "status": "unavailable",
            "validator": "css_static_checks",
            "items": [],
            "reason": "Install dependencies from ml/requirements.txt.",
        }

    definitions: set[str] = set()
    references: list[tuple[str, int, int]] = []

    def inspect_tokens(tokens: list[object]) -> None:
        for token in tokens:
            if getattr(token, "type", None) != "function":
                continue
            arguments = list(getattr(token, "arguments", []))
            first = next(
                (item for item in arguments if getattr(item, "type", None) not in {"whitespace", "comment"}),
                None,
            )
            if getattr(token, "name", "").lower() == "var" and getattr(first, "type", None) == "ident":
                property_name = str(getattr(first, "value", ""))
                has_fallback = any(
                    getattr(item, "type", None) == "literal" and getattr(item, "value", None) == ","
                    for item in arguments
                )
                if property_name.startswith("--") and not has_fallback:
                    references.append(
                        (
                            property_name,
                            int(getattr(token, "source_line", 1)),
                            int(getattr(token, "source_column", 1)),
                        )
                    )
            inspect_tokens(arguments)
            nested_content = getattr(token, "content", None)
            if isinstance(nested_content, list):
                inspect_tokens(nested_content)

    def inspect_rules(rules: list[object]) -> None:
        for rule in rules:
            rule_type = getattr(rule, "type", None)
            if rule_type == "qualified-rule":
                declarations = tinycss2.parse_declaration_list(
                    rule.content, skip_comments=True, skip_whitespace=True
                )
                for declaration in declarations:
                    if getattr(declaration, "type", None) == "declaration":
                        name = str(getattr(declaration, "name", ""))
                        if name.startswith("--"):
                            definitions.add(name)
                        inspect_tokens(list(getattr(declaration, "value", [])))
            elif rule_type == "at-rule" and getattr(rule, "content", None) is not None:
                nested = tinycss2.parse_rule_list(
                    rule.content, skip_comments=True, skip_whitespace=True
                )
                inspect_rules(nested)

    stylesheet = tinycss2.parse_stylesheet(source, skip_comments=True, skip_whitespace=True)
    inspect_rules(stylesheet)

    items = [
        _semantic_item(
            "CSS_UNDEFINED_CUSTOM_PROPERTY",
            f'Custom property "{name}" is referenced with var() but no definition or fallback was found in this stylesheet.',
            line,
            column,
        )
        for name, line, column in references
        if name not in definitions
    ]
    return {
        "status": "available",
        "validator": "css_static_checks",
        "items": items[:50],
        "note": "These checks scan definitions across this stylesheet and do not model CSS cascade or external stylesheets.",
    }


def _semantic_item(code: str, message: str, line: int, column: int) -> dict[str, object]:
    return {
        "source": "semantic_validator",
        "code": code,
        "message": message,
        "line": line,
        "column": column,
        "severity": "warning",
        "is_model_prediction": False,
        "is_confirmed_semantic_error": False,
    }
