"""Deterministic parser diagnostics, kept separate from ML predictions."""

from __future__ import annotations

import re
from typing import Any


def diagnose_source(language: str, source: str | None) -> dict[str, object]:
    """Return parser findings for one language without interpreting ML scores."""
    if language not in {"html", "css", "javascript"}:
        raise ValueError(f"unsupported language: {language!r}")
    if source is None:
        return {"status": "not_provided", "parser": None, "items": []}
    if not isinstance(source, str):
        raise ValueError(f"{language} source must be a string or None")
    if not source.strip():
        return {"status": "empty", "parser": None, "items": []}

    if language == "html":
        return _html_diagnostics(source)
    if language == "css":
        return _css_diagnostics(source)
    return _javascript_diagnostics(source)


def _item(
    language: str,
    parser: str,
    code: str,
    message: str,
    line: int | None,
    column: int | None,
) -> dict[str, object]:
    return {
        "language": language,
        "source": "deterministic_parser",
        "parser": parser,
        "code": code,
        "message": message,
        "line": line,
        "column": column,
        "is_model_prediction": False,
        "is_confirmed_compiler_error": False,
    }


def _unavailable(parser: str, error: ImportError) -> dict[str, object]:
    return {
        "status": "unavailable",
        "parser": parser,
        "items": [],
        "reason": "Install dependencies from ml/requirements.txt.",
    }


def _html_diagnostics(source: str) -> dict[str, object]:
    try:
        import html5lib
    except ImportError as error:
        return _unavailable("html5lib", error)

    parser = html5lib.HTMLParser(strict=False)
    if re.search(r"<!doctype\s+html\b|<html(?:\s|>)", source, re.IGNORECASE):
        parser.parse(source)
    else:
        parser.parseFragment(source)
    items = []
    for position, error_code, details in parser.errors[:50]:
        line, column = position
        detail_text = ", ".join(
            f"{key}={value}" for key, value in sorted(details.items())
        )
        message = f"HTML5 parser reported {error_code}"
        if detail_text:
            message += f" ({detail_text})"
        items.append(
            _item(
                "html",
                "html5lib",
                f"HTML_PARSE_{str(error_code).upper().replace('-', '_')}",
                message,
                int(line),
                int(column),
            )
        )
    return {"status": "available", "parser": "html5lib", "items": items}


def _css_diagnostics(source: str) -> dict[str, object]:
    try:
        import tinycss2
    except ImportError as error:
        return _unavailable("tinycss2", error)

    items: list[dict[str, object]] = []

    def add_errors(nodes: list[Any]) -> None:
        for node in nodes:
            if getattr(node, "type", None) == "error":
                kind = str(getattr(node, "kind", "parse_error"))
                items.append(
                    _item(
                        "css",
                        "tinycss2",
                        f"CSS_PARSE_{kind.upper().replace('-', '_')}",
                        f"tinycss2 reported a CSS syntax issue: {kind}.",
                        getattr(node, "source_line", None),
                        getattr(node, "source_column", None),
                    )
                )

    def inspect_rules(rules: list[Any]) -> None:
        add_errors(rules)
        for rule in rules:
            rule_type = getattr(rule, "type", None)
            if rule_type == "qualified-rule":
                declarations = tinycss2.parse_declaration_list(
                    rule.content, skip_comments=True, skip_whitespace=True
                )
                add_errors(declarations)
                for declaration in declarations:
                    add_errors(getattr(declaration, "value", []))
            elif rule_type == "at-rule" and getattr(rule, "content", None) is not None:
                nested = tinycss2.parse_rule_list(
                    rule.content, skip_comments=True, skip_whitespace=True
                )
                inspect_rules(nested)

    rules = tinycss2.parse_stylesheet(
        source, skip_comments=True, skip_whitespace=True
    )
    inspect_rules(rules)

    items.extend(_css_brace_diagnostics(source))

    return {"status": "available", "parser": "tinycss2", "items": items[:50]}


def _css_brace_diagnostics(source: str) -> list[dict[str, object]]:
    """Report unmatched CSS block braces while ignoring strings and comments."""
    stack: list[int] = []
    comment = False
    quote: str | None = None
    string_start: int | None = None
    escaped = False
    unmatched_close: int | None = None
    index = 0

    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if comment:
            if char == "*" and following == "/":
                comment = False
                index += 2
                continue
            index += 1
            continue
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
                string_start = None
            index += 1
            continue
        if char == "/" and following == "*":
            comment = True
            index += 2
            continue
        if char in {"'", '"'}:
            quote = char
            string_start = index
        elif char == "{":
            stack.append(index)
        elif char == "}":
            if stack:
                stack.pop()
            elif unmatched_close is None:
                unmatched_close = index
        index += 1

    items: list[dict[str, object]] = []
    if quote is not None and string_start is not None:
        line, column = _line_column(source, string_start)
        items.append(
            _item(
                "css",
                "tinycss2",
                "CSS_UNTERMINATED_STRING",
                "CSS string is not terminated before end of input.",
                line,
                column,
            )
        )
    if stack and quote is None:
        line, column = _line_column(source, len(source))
        items.append(
            _item(
                "css",
                "tinycss2",
                "CSS_UNCLOSED_BLOCK",
                "CSS block is missing a closing brace before end of input.",
                line,
                column,
            )
        )
    if unmatched_close is not None:
        line, column = _line_column(source, unmatched_close)
        items.append(
            _item(
                "css",
                "tinycss2",
                "CSS_UNEXPECTED_CLOSING_BRACE",
                "CSS contains a closing brace without a matching opening brace.",
                line,
                column,
            )
        )
    return items


def _line_column(source: str, offset: int) -> tuple[int, int]:
    line = source.count("\n", 0, offset) + 1
    previous_newline = source.rfind("\n", 0, offset)
    return line, offset - previous_newline


def _javascript_diagnostics(source: str) -> dict[str, object]:
    try:
        import esprima
        from esprima.error_handler import Error as EsprimaError
    except ImportError as error:
        return _unavailable("esprima", error)

    try:
        esprima.parseScript(source, {"loc": True})
    except EsprimaError as error:
        description = getattr(error, "description", str(error))
        normalized_description = str(description).lower()
        if "illegal" in normalized_description or "unterminated string" in normalized_description:
            code = "JAVASCRIPT_UNTERMINATED_STRING"
        elif "unexpected end of input" in normalized_description:
            code = "JAVASCRIPT_UNCLOSED_DELIMITER"
        elif "unexpected token" in normalized_description:
            code = "JAVASCRIPT_UNEXPECTED_TOKEN"
        else:
            code = "JAVASCRIPT_PARSE_ERROR"
        if code != "JAVASCRIPT_UNTERMINATED_STRING" and _javascript_has_unclosed_delimiter(
            esprima, source
        ):
            code = "JAVASCRIPT_UNCLOSED_DELIMITER"
        line = getattr(error, "lineNumber", None)
        column = getattr(error, "column", None)
        item = _item(
            "javascript",
            "esprima",
            code,
            str(description),
            int(line) if line is not None else None,
            int(column) if column is not None else None,
        )
        return {"status": "available", "parser": "esprima", "items": [item]}
    return {"status": "available", "parser": "esprima", "items": []}


def _javascript_has_unclosed_delimiter(esprima: Any, source: str) -> bool:
    """Use Esprima's tokenizer to spot an unmatched (), [], or {} pair."""
    try:
        tokens = esprima.tokenize(source, {"tolerant": True})
    except Exception:
        return False
    closing_for = {"(": ")", "[": "]", "{": "}"}
    stack: list[str] = []
    for token in tokens:
        if getattr(token, "type", None) != "Punctuator":
            continue
        value = getattr(token, "value", None)
        if value in closing_for:
            stack.append(value)
        elif value in closing_for.values():
            if not stack or closing_for[stack[-1]] != value:
                return False
            stack.pop()
    return bool(stack)
