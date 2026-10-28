# ML error-category predictor

The ML component is a lightweight, parser-assisted classifier that ranks likely
HTML, CSS, and JavaScript error categories. The local backend calls this
analyzer and returns the model rankings separately from deterministic parser
findings. It does not claim that a model prediction is a confirmed compiler
error.

## Repository layout

The model and its reproducible training/evaluation code live under `ml/`.
The local HTTP server is in `backend/`, the browser interface is in `frontend/`,
and the setup and API contract are in [the web app guide](web-app.md).

## Input and output contract

### Try the model locally

Before a backend or frontend is available, run this from the repository root:

```powershell
python -m ml.demo --top-k 1
```

Paste HTML, CSS, and JavaScript source at the prompts. Enter `END` on its own
line after each snippet; enter `END` immediately to skip a language. The command
prints the same JSON shape described below. Complete HTML documents use the
HTML document parser, while snippets use the fragment parser. It runs locally
and does not start a web server.

Call `ErrorAnalyzer.analyze()` with any combination of source strings:

```python
from ml import ErrorAnalyzer

analyzer = ErrorAnalyzer()
result = analyzer.analyze(
    html="<div>Welcome",
    css=".card { color red; }",
    javascript="const result = compute(4, 2;",
    top_k=1,
)
```

The backend may expose the same fields in a JSON request:

```json
{
  "html": "<div>Welcome",
  "css": ".card { color red; }",
  "javascript": "const result = compute(4, 2;",
  "top_k": 1
}
```

The response has two separate sections:

```json
{
  "model": {
    "algorithm": "multinomial-naive-bayes",
    "feature_mode": "token_parser",
    "confidence_note": "Smoothed Naive Bayes scores are not calibrated probabilities. Predictions are not confirmed compiler errors."
  },
  "predictions": {
    "html": [
      {
        "language": "html",
        "category": "html_unclosed_tag",
        "confidence": 0.544945,
        "source": "model_prediction",
        "is_confirmed": false
      }
    ],
    "css": [
      {
        "language": "css",
        "category": "css_missing_colon",
        "confidence": 0.999493,
        "source": "model_prediction",
        "is_confirmed": false
      }
    ],
    "javascript": [
      {
        "language": "javascript",
        "category": "javascript_unclosed_delimiter",
        "confidence": 0.998105,
        "source": "model_prediction",
        "is_confirmed": false
      }
    ]
  },
  "deterministic_diagnostics": {
    "html": {
      "status": "available",
      "parser": "html5lib",
      "items": [
        {
          "language": "html",
          "source": "deterministic_parser",
          "parser": "html5lib",
          "code": "HTML_PARSE_EXPECTED_CLOSING_TAG_BUT_GOT_EOF",
          "message": "HTML5 parser reported expected-closing-tag-but-got-eof",
          "line": 1,
          "column": 12,
          "is_model_prediction": false,
          "is_confirmed_compiler_error": false
        }
      ]
    },
    "css": {
      "status": "available",
      "parser": "tinycss2",
      "items": [
        {
          "language": "css",
          "source": "deterministic_parser",
          "parser": "tinycss2",
          "code": "CSS_PARSE_INVALID",
          "message": "tinycss2 reported a CSS syntax issue: invalid.",
          "line": 1,
          "column": 15,
          "is_model_prediction": false,
          "is_confirmed_compiler_error": false
        }
      ]
    },
    "javascript": {
      "status": "available",
      "parser": "esprima",
      "items": [
        {
          "language": "javascript",
          "source": "deterministic_parser",
          "parser": "esprima",
          "code": "JAVASCRIPT_UNCLOSED_DELIMITER",
          "message": "Line 1: Unexpected token ;",
          "line": 1,
          "column": 28,
          "is_model_prediction": false,
          "is_confirmed_compiler_error": false
        }
      ]
    }
  }
}
```

The response above is the actual output from the included saved model and parser
dependencies for this request. Model entries always have `is_confirmed: false`.
Parser entries carry `source: deterministic_parser` and
`is_model_prediction: false`. HTML5 parser findings can be recoverable and are
not automatically fatal compiler errors. An unavailable parser is reported
with `status: unavailable`, rather than silently returning no findings.

A complete HTML document with a doctype is parsed as a document rather than a
fragment. The valid example used in the regression test returns
`no_likely_error` with an empty HTML diagnostics list.

The selected model uses token features plus the deterministic parser's
diagnostic codes as input features (`token_parser`). The parser diagnostics are
still returned in their own response section; the model uses them to rank a
category, and its ranking is still not a confirmed compiler result. The
classifier also reuses each request's already-computed diagnostics so a
backend integration does not parse the same source twice.

### Current prediction categories

| Language | Categories |
| --- | --- |
| HTML | `html_unclosed_tag`, `html_unexpected_end_tag`, `html_duplicate_attribute`, `no_likely_error` |
| CSS | `css_missing_colon`, `css_unclosed_block`, `css_unterminated_string`, `no_likely_error` |
| JavaScript | `javascript_unclosed_delimiter`, `javascript_unterminated_string`, `javascript_unexpected_token`, `no_likely_error` |

The model returns up to `top_k` ranked categories for each non-empty source.
Confidence is a smoothed Naive Bayes score; it is not calibrated and should not
be treated as a probability of a real compiler failure.

The web backend extends the `ErrorAnalyzer` response with a separate
`semantic_diagnostics` object for HTML, CSS, and JavaScript, plus a
`model.benchmark` summary loaded from `ml/artifacts/evaluation.json`. Those
static semantic results are not training labels and are not fed into the
classifier.

## Setup, training, and evaluation

Use Python 3.10 or newer. From the repository root in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ml/requirements.txt
.\.venv\Scripts\python.exe -m ml.generate_data
.\.venv\Scripts\python.exe -m ml.train
.\.venv\Scripts\python.exe -m ml.evaluate
.\.venv\Scripts\python.exe -m unittest discover -s ml\tests -v
```

Use the `.venv\Scripts\python.exe` path directly in PowerShell; activation is
optional and may be restricted by the machine's execution policy.

`python -m ml.generate_data` rebuilds the checked-in corpus deterministically
with seed `20261025`. `python -m ml.train` compares two feature modes and four
smoothing values on the validation split, then refits the selected model on the
combined train and validation splits. It writes
`ml/artifacts/error_classifier.json`. `python -m ml.evaluate` repeats model
selection without using the test split, evaluates on the held-out data, compares
with a token-only baseline, and writes `ml/artifacts/evaluation.json`. The Naive
Bayes algorithm uses Python's standard library. The selected parser-assisted
feature mode and deterministic diagnostics use pinned parser dependencies:
html5lib for HTML, tinycss2 for CSS, and Esprima for JavaScript.

### Current result on the synthetic held-out split

The checked-in corpus has 2,664 examples: 2,592 grammar-generated and parser-
checked examples plus the original 72 hand-authored examples. The split has
1,773 training, 432 validation, and 459 test examples. The generated examples
are grouped by template family, and no family crosses splits. The selected
configuration was `token_parser` with `alpha=0.25`, chosen on validation data.
On the held-out test set it scored **0.9325 accuracy** and **0.9353 macro-F1**.
Accuracy was HTML **1.0000**, CSS **0.9542**, and JavaScript **0.8431**. The
token-only reference scored **0.7233 accuracy** and **0.7309 macro-F1** on the
same test examples. The separately reported 27-example hand-authored test
portion scored **0.9630 accuracy** and **0.9619 macro-F1**.

The selected configuration scored **1.0000 accuracy** and **1.0000 macro-F1**
on the validation split. Because this is generated synthetic data, that perfect
validation score is evidence about the controlled mutation patterns only; it is
not evidence of perfect or near-perfect results on real code.

These metrics describe parser-checked synthetic examples. They do not estimate
performance on code from students, real repositories, or the final project.
The high validation result is consistent with a controlled synthetic task and
must not be read as proof of real-world accuracy.

## Data and evaluation limitations

The repository began without a real labeled code dataset. The reproducible
`ml/generate_data.py` script creates controlled examples from 18 templates per
language, including complete HTML documents, and introduces one targeted
mutation at a time. Parser checks verify the intended diagnostic and clean
examples are parser-clean. The original
hand-authored synthetic data is preserved in `ml/data/synthetic_examples.jsonl`
and included as a separately identified source. All records are marked with
their origin. Template-family splits reduce near-duplicate leakage, but the
dataset remains synthetic. Replace or augment it with a properly licensed,
reviewed, independently collected dataset before making claims about practical
accuracy.

The classifier is a small multinomial Naive Bayes model. Validation selects
between token-only and token-plus-character/parser feature sets and tunes the
smoothing parameter. It needs no pretrained model download. It only predicts
the listed categories; it does not fix code, validate browser behavior, check
CSS property support, or prove JavaScript variables are defined. Esprima parser
diagnostics are limited to the syntax it supports (ECMAScript 2017 script
mode). Keep parser findings and model predictions in separate backend response
fields.

Repository source and user source should be treated as untrusted input. Do not
execute submitted code as part of model inference.
