"""Conservative undeclared-identifier checks for JavaScript source."""

from __future__ import annotations

from dataclasses import dataclass, field


KNOWN_GLOBALS = set(
    """
    undefined NaN Infinity globalThis eval isFinite isNaN parseFloat parseInt
    decodeURI decodeURIComponent encodeURI encodeURIComponent escape unescape
    Object Function Boolean Symbol Error AggregateError EvalError RangeError
    ReferenceError SyntaxError TypeError URIError Number BigInt Math Date String
    RegExp Array Int8Array Uint8Array Uint8ClampedArray Int16Array Uint16Array
    Int32Array Uint32Array Float32Array Float64Array BigInt64Array BigUint64Array
    ArrayBuffer SharedArrayBuffer DataView JSON Promise Set WeakSet Map WeakMap
    WeakRef FinalizationRegistry Proxy Reflect Atomics Intl WebAssembly
    window self document navigator location history console alert confirm prompt
    fetch XMLHttpRequest WebSocket Headers Request Response URL URLSearchParams
    FormData File FileReader Blob AbortController MutationObserver
    IntersectionObserver ResizeObserver Event EventTarget CustomEvent HTMLElement
    Element Node NodeList HTMLCollection DOMParser setTimeout clearTimeout
    setInterval clearInterval requestAnimationFrame cancelAnimationFrame
    queueMicrotask performance crypto localStorage sessionStorage structuredClone
    btoa atob process Buffer require module exports __dirname __filename global
    setImmediate clearImmediate
    """.split()
)


@dataclass
class _Scope:
    kind: str
    parent: "_Scope | None" = None
    names: set[str] = field(default_factory=set)
    references: list[tuple[str, int, int]] = field(default_factory=list)

    def var_scope(self) -> "_Scope":
        scope = self
        while scope.parent is not None and scope.kind not in {"program", "function"}:
            scope = scope.parent
        return scope

    def declares(self, name: str) -> bool:
        return name in self.names or (self.parent is not None and self.parent.declares(name))


class _JavaScriptInspector:
    def __init__(self) -> None:
        self.references: list[tuple[_Scope, str, int, int]] = []

    def visit(
        self,
        node: object,
        scope: _Scope,
        *,
        parent_type: str | None = None,
        parent_node: dict[str, object] | None = None,
        parent_key: str | None = None,
        function_body: bool = False,
    ) -> None:
        if not isinstance(node, dict) or not isinstance(node.get("type"), str):
            return
        kind = str(node["type"])

        if kind == "Program":
            for statement in node.get("body", []):
                self.visit(statement, scope)
            return

        if kind in {"FunctionDeclaration", "FunctionExpression", "ArrowFunctionExpression"}:
            function_id = node.get("id")
            if kind == "FunctionDeclaration":
                self._declare_pattern(function_id, scope)
            child = _Scope("function", scope)
            if kind == "FunctionExpression":
                self._declare_pattern(function_id, child)
            if kind != "ArrowFunctionExpression":
                child.names.add("arguments")
            for parameter in node.get("params", []):
                self._declare_pattern(parameter, child)
            for parameter in node.get("params", []):
                self._visit_pattern_expressions(parameter, child)
            body = node.get("body")
            if isinstance(body, dict) and body.get("type") == "BlockStatement":
                for statement in body.get("body", []):
                    self.visit(statement, child)
            else:
                self.visit(body, child)
            return

        if kind == "BlockStatement":
            child = scope if function_body else _Scope("block", scope)
            for statement in node.get("body", []):
                self.visit(statement, child)
            return

        if kind == "VariableDeclaration":
            declaration_scope = scope.var_scope() if node.get("kind") == "var" else scope
            for declaration in node.get("declarations", []):
                if not isinstance(declaration, dict):
                    continue
                pattern = declaration.get("id")
                self._declare_pattern(pattern, declaration_scope)
                self._visit_pattern_expressions(pattern, scope)
                self.visit(declaration.get("init"), scope)
            return

        if kind in {"ClassDeclaration", "ClassExpression"}:
            if kind == "ClassDeclaration":
                self._declare_pattern(node.get("id"), scope)
            self.visit(node.get("superClass"), scope)
            class_scope = _Scope("block", scope)
            self._declare_pattern(node.get("id"), class_scope)
            self.visit(node.get("body"), class_scope)
            return

        if kind == "CatchClause":
            catch_scope = _Scope("block", scope)
            self._declare_pattern(node.get("param"), catch_scope)
            self._visit_pattern_expressions(node.get("param"), catch_scope)
            body = node.get("body")
            if isinstance(body, dict):
                for statement in body.get("body", []):
                    self.visit(statement, catch_scope)
            return

        if kind in {"ForStatement", "ForInStatement", "ForOfStatement"}:
            loop_scope = _Scope("block", scope)
            for key in ("init", "left", "right", "test", "update", "body"):
                if key in node:
                    self.visit(node[key], loop_scope, parent_type=kind, parent_node=node, parent_key=key)
            return

        if kind == "SwitchStatement":
            self.visit(node.get("discriminant"), scope)
            switch_scope = _Scope("block", scope)
            for case in node.get("cases", []):
                self.visit(case, switch_scope)
            return

        if kind == "Identifier":
            if self._is_reference(parent_type, parent_node, parent_key):
                loc = node.get("loc", {})
                start = loc.get("start", {}) if isinstance(loc, dict) else {}
                line = int(start.get("line", 1)) if isinstance(start, dict) else 1
                column = int(start.get("column", 0)) + 1 if isinstance(start, dict) else 1
                self.references.append((scope, str(node.get("name", "")), line, column))
            return

        if kind == "MetaProperty":
            return

        for key, value in node.items():
            if key in {"type", "loc", "range", "raw", "tokens", "comments"}:
                continue
            if self._skip_child_identifier(kind, node, key):
                continue
            if isinstance(value, list):
                for child in value:
                    self.visit(child, scope, parent_type=kind, parent_node=node, parent_key=key)
            elif isinstance(value, dict):
                self.visit(value, scope, parent_type=kind, parent_node=node, parent_key=key)

    def _declare_pattern(self, pattern: object, scope: _Scope) -> None:
        if not isinstance(pattern, dict):
            return
        kind = pattern.get("type")
        if kind == "Identifier":
            name = pattern.get("name")
            if isinstance(name, str):
                scope.names.add(name)
        elif kind in {"ArrayPattern", "ArrayExpression"}:
            for element in pattern.get("elements", []):
                self._declare_pattern(element, scope)
        elif kind in {"ObjectPattern", "ObjectExpression"}:
            for prop in pattern.get("properties", []):
                if isinstance(prop, dict) and prop.get("type") == "RestElement":
                    self._declare_pattern(prop.get("argument"), scope)
                elif isinstance(prop, dict):
                    self._declare_pattern(prop.get("value"), scope)
        elif kind in {"RestElement", "SpreadElement"}:
            self._declare_pattern(pattern.get("argument"), scope)
        elif kind == "AssignmentPattern":
            self._declare_pattern(pattern.get("left"), scope)

    def _visit_pattern_expressions(self, pattern: object, scope: _Scope) -> None:
        if not isinstance(pattern, dict):
            return
        kind = pattern.get("type")
        if kind == "AssignmentPattern":
            self.visit(pattern.get("right"), scope)
            self._visit_pattern_expressions(pattern.get("left"), scope)
        elif kind in {"ArrayPattern", "ArrayExpression"}:
            for element in pattern.get("elements", []):
                self._visit_pattern_expressions(element, scope)
        elif kind in {"ObjectPattern", "ObjectExpression"}:
            for prop in pattern.get("properties", []):
                if not isinstance(prop, dict):
                    continue
                if prop.get("computed"):
                    self.visit(prop.get("key"), scope)
                self._visit_pattern_expressions(prop.get("value", prop.get("argument")), scope)
        elif kind in {"RestElement", "SpreadElement"}:
            self._visit_pattern_expressions(pattern.get("argument"), scope)

    @staticmethod
    def _is_reference(
        parent_type: str | None,
        parent_node: dict[str, object] | None,
        parent_key: str | None,
    ) -> bool:
        if parent_type in {"VariableDeclarator", "FunctionDeclaration", "FunctionExpression", "ClassDeclaration", "ClassExpression", "CatchClause", "LabeledStatement", "BreakStatement", "ContinueStatement"}:
            if parent_key in {"id", "params", "param", "label"}:
                return False
        if parent_type == "MemberExpression" and parent_key == "property":
            return bool(parent_node and parent_node.get("computed", False))
        if parent_type in {"Property", "MethodDefinition", "PropertyDefinition"} and parent_key == "key":
            if parent_type == "Property" and parent_node is not None and parent_node.get("shorthand"):
                return False
            return bool(parent_node and parent_node.get("computed", False))
        if parent_type == "MetaProperty":
            return False
        return True

    @staticmethod
    def _skip_child_identifier(kind: str, node: dict[str, object], key: str) -> bool:
        if kind in {"LabeledStatement", "BreakStatement", "ContinueStatement"} and key == "label":
            return True
        if kind == "Property" and key == "key" and not node.get("computed", False):
            return True
        if kind in {"MethodDefinition", "PropertyDefinition"} and key == "key" and not node.get("computed", False):
            return True
        if kind == "MemberExpression" and key == "property" and not node.get("computed", False):
            return True
        return False


def validate_javascript_semantics(
    source: str | None,
    *,
    parser_findings: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Report identifiers that cannot be resolved in this script's known scopes."""
    if source is None:
        return {"status": "not_provided", "validator": "javascript_static_checks", "items": []}
    if not isinstance(source, str):
        raise ValueError("JavaScript source must be a string or None")
    if not source.strip():
        return {"status": "empty", "validator": "javascript_static_checks", "items": []}
    if parser_findings:
        return {
            "status": "skipped_syntax_error",
            "validator": "javascript_static_checks",
            "items": [],
            "note": "Fix the JavaScript syntax finding before running identifier checks.",
        }

    try:
        import esprima

        tree = esprima.parseScript(source, {"loc": True}).toDict()
    except ImportError:
        return {
            "status": "unavailable",
            "validator": "javascript_static_checks",
            "items": [],
            "reason": "Install dependencies from ml/requirements.txt.",
        }
    except Exception:
        return {
            "status": "skipped_syntax_error",
            "validator": "javascript_static_checks",
            "items": [],
            "note": "Fix the JavaScript syntax finding before running identifier checks.",
        }

    root = _Scope("program")
    inspector = _JavaScriptInspector()
    inspector.visit(tree, root)
    items: list[dict[str, object]] = []
    for scope, name, line, column in inspector.references:
        if name and name not in KNOWN_GLOBALS and not scope.declares(name):
            items.append(
                {
                    "source": "semantic_validator",
                    "code": "JAVASCRIPT_UNDECLARED_IDENTIFIER",
                    "message": f'Identifier "{name}" is not declared in this source or in the known browser/Node.js globals.',
                    "line": line,
                    "column": column,
                    "severity": "warning",
                    "is_model_prediction": False,
                    "is_confirmed_semantic_error": False,
                }
            )
    return {
        "status": "available",
        "validator": "javascript_static_checks",
        "items": items[:50],
        "note": "This is a conservative single-file check; project imports and custom runtime globals are not resolved.",
    }
