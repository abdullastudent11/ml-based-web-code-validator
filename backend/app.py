"""Small standard-library HTTP server for the HTML/CSS/JavaScript analyzer."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ml.analyzer import ErrorAnalyzer
from .javascript_semantic import validate_javascript_semantics
from .semantic import validate_css_semantics, validate_html_semantics


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = ROOT / "frontend"
EVALUATION_PATH = ROOT / "ml" / "artifacts" / "evaluation.json"
MAX_REQUEST_BYTES = 256 * 1024
DEFAULT_TOP_K = 3
MAX_TOP_K = 5
LOGGER = logging.getLogger("web_code_validator")


def load_model_benchmark() -> dict[str, object]:
    """Expose held-out evaluation context without implying real-world accuracy."""
    try:
        report = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
        overall = report["overall"]
        selected = report["selected_model"]
        selected_configuration = report["model_selection"]["selected"]
        reference = report["reference_baseline"]["overall"]
        split_counts = report["evaluation_data"]["split_counts"]
        test_examples = int(overall["examples"])
        by_language = {
            language: {
                "examples": int(metrics["examples"]),
                "accuracy": float(metrics["accuracy"]),
                "macro_precision": float(metrics["macro_precision"]),
                "macro_recall": float(metrics["macro_recall"]),
                "macro_f1": float(metrics["macro_f1"]),
                "per_class": [
                    {
                        "category": category,
                        "support": int(scores["support"]),
                        "precision": float(scores["precision"]),
                        "recall": float(scores["recall"]),
                        "f1": float(scores["f1"]),
                    }
                    for category, scores in metrics["per_class"].items()
                ],
            }
            for language, metrics in report["by_language"].items()
        }
        return {
            "status": "available",
            "dataset": "synthetic_holdout",
            "test_examples": test_examples,
            "training_split_examples": int(split_counts["train"]),
            "validation_examples": int(split_counts["validation"]),
            "training_examples": int(selected["training_examples_including_validation"]),
            "accuracy": float(overall["accuracy"]),
            "macro_precision": float(overall["macro_precision"]),
            "macro_recall": float(overall["macro_recall"]),
            "macro_f1": float(overall["macro_f1"]),
            "feature_mode": str(selected["feature_mode"]),
            "smoothing_alpha": float(selected["alpha"]),
            "selected_on_validation": {
                "accuracy": float(selected_configuration["validation_accuracy"]),
                "macro_f1": float(selected_configuration["validation_macro_f1"]),
            },
            "dataset_splits": {
                "train": int(split_counts["train"]),
                "validation": int(split_counts["validation"]),
                "test": test_examples,
            },
            "by_language": by_language,
            "reference_baseline": {
                "algorithm": "Token-only Multinomial Naive Bayes",
                "test_examples": int(reference["examples"]),
                "accuracy": float(reference["accuracy"]),
                "macro_f1": float(reference["macro_f1"]),
            },
            "limitations": list(report.get("limitations", [])),
            "note": (
                "Metrics are from held-out synthetic examples. They do not estimate "
                "accuracy on real-world source code."
            ),
        }
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {
            "status": "unavailable",
            "dataset": "synthetic_holdout",
            "note": "The saved evaluation report is unavailable.",
        }


MODEL_BENCHMARK = load_model_benchmark()


def analyze_bundle(
    analyzer: ErrorAnalyzer,
    sources: dict[str, str | None],
    top_k: int,
) -> dict[str, object]:
    """Combine the ML response with deterministic cross-language semantics."""
    result = analyzer.analyze(**sources, top_k=top_k)
    javascript_items = result["deterministic_diagnostics"]["javascript"]["items"]
    result["semantic_diagnostics"] = {
        "html": validate_html_semantics(sources["html"]),
        "css": validate_css_semantics(sources["css"]),
        "javascript": validate_javascript_semantics(
            sources["javascript"],
            parser_findings=javascript_items,
        ),
    }
    result["model"]["benchmark"] = MODEL_BENCHMARK
    return result


class AnalyzerRequestHandler(BaseHTTPRequestHandler):
    """Serve the frontend and a JSON API from the same origin."""

    server_version = "WebCodeValidator/1.0"
    analyzer: ErrorAnalyzer

    def do_GET(self) -> None:
        route = urlsplit(self.path).path
        if route == "/api/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "web-code-validator",
                    "model": self.analyzer.classifier.algorithm,
                    "feature_mode": self.analyzer.classifier.feature_mode,
                    "benchmark": MODEL_BENCHMARK,
                },
            )
            return
        self._serve_frontend(route)

    def do_POST(self) -> None:
        route = urlsplit(self.path).path
        if route != "/api/analyze":
            self._send_error_json(HTTPStatus.NOT_FOUND, "NOT_FOUND", "Endpoint not found.")
            return

        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._send_error_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "UNSUPPORTED_MEDIA_TYPE",
                "Send the request as application/json.",
            )
            return

        raw_length = self.headers.get("Content-Length")
        try:
            content_length = int(raw_length or "0")
        except ValueError:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "INVALID_LENGTH", "Invalid request length.")
            return
        if content_length <= 0:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "EMPTY_BODY", "The request body is empty.")
            return
        if content_length > MAX_REQUEST_BYTES:
            self._send_error_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                "REQUEST_TOO_LARGE",
                f"Keep the request body under {MAX_REQUEST_BYTES // 1024} KB.",
            )
            return

        try:
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_error_json(HTTPStatus.BAD_REQUEST, "INVALID_JSON", "The request body must be valid UTF-8 JSON.")
            return
        if not isinstance(payload, dict):
            self._send_error_json(HTTPStatus.BAD_REQUEST, "INVALID_BODY", "The JSON body must be an object.")
            return

        allowed_fields = {"html", "css", "javascript", "top_k"}
        unexpected_fields = sorted(set(payload) - allowed_fields)
        if unexpected_fields:
            self._send_error_json(
                HTTPStatus.BAD_REQUEST,
                "UNKNOWN_FIELDS",
                "Unsupported request field(s): " + ", ".join(unexpected_fields),
            )
            return

        sources: dict[str, str | None] = {}
        for language in ("html", "css", "javascript"):
            source = payload.get(language)
            if source is not None and not isinstance(source, str):
                self._send_error_json(
                    HTTPStatus.BAD_REQUEST,
                    "INVALID_SOURCE",
                    f"{language} must be a string or null.",
                )
                return
            sources[language] = source
        if not any(source and source.strip() for source in sources.values()):
            self._send_error_json(
                HTTPStatus.BAD_REQUEST,
                "NO_SOURCE",
                "Enter HTML, CSS, or JavaScript before running the analysis.",
            )
            return

        top_k = payload.get("top_k", DEFAULT_TOP_K)
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= MAX_TOP_K:
            self._send_error_json(
                HTTPStatus.BAD_REQUEST,
                "INVALID_TOP_K",
                f"top_k must be a whole number from 1 to {MAX_TOP_K}.",
            )
            return

        try:
            result = analyze_bundle(self.analyzer, sources, top_k)
        except (ValueError, TypeError) as error:
            LOGGER.info("Analysis request rejected: %s", error)
            self._send_error_json(HTTPStatus.BAD_REQUEST, "INVALID_REQUEST", str(error))
            return
        except Exception:
            LOGGER.exception("Unexpected analysis failure")
            self._send_error_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "ANALYSIS_FAILED",
                "The analysis could not be completed. Please try again.",
            )
            return
        self._send_json(HTTPStatus.OK, result)

    def _serve_frontend(self, route: str) -> None:
        relative = "index.html" if route in {"", "/"} else unquote(route).lstrip("/")
        try:
            requested = (FRONTEND_ROOT / relative).resolve()
            requested.relative_to(FRONTEND_ROOT.resolve())
            if not requested.is_file():
                self._send_error_json(HTTPStatus.NOT_FOUND, "NOT_FOUND", "Page not found.")
                return
        except ValueError:
            self._send_error_json(HTTPStatus.NOT_FOUND, "NOT_FOUND", "Page not found.")
            return
        except (OSError, RuntimeError):
            self._send_error_json(HTTPStatus.NOT_FOUND, "NOT_FOUND", "Page not found.")
            return

        content_type, _ = mimetypes.guess_type(os.fspath(requested))
        body = requested.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: HTTPStatus, code: str, message: str) -> None:
        self._send_json(status, {"error": {"code": code, "message": message}})

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'")

    def log_message(self, format_string: str, *args: object) -> None:
        LOGGER.info("%s - %s", self.address_string(), format_string % args)


def main() -> None:
    """Load the model once and start the local development server."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    host = os.environ.get("WEB_VALIDATOR_HOST", "127.0.0.1")
    port = int(os.environ.get("WEB_VALIDATOR_PORT", "8000"))
    AnalyzerRequestHandler.analyzer = ErrorAnalyzer()
    server = ThreadingHTTPServer((host, port), AnalyzerRequestHandler)
    LOGGER.info("Web Code Validator ready at http://%s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Shutting down the web server")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
