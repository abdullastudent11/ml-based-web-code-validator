# Web application and API

The project combines the saved ML model with parser diagnostics behind a local
JSON API. The browser interface is served by the same Python process, so the
frontend and API use one origin and need no separate frontend build step.

## Start it locally

Use Python 3.10 or newer. In PowerShell, from the repository root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ml/requirements.txt
.\.venv\Scripts\python.exe -m backend
```

Using `.venv\Scripts\python.exe` directly avoids PowerShell execution-policy
errors from `Activate.ps1` and ensures both installation and startup use the
project environment.

Then open http://127.0.0.1:8000. The backend loads
`ml/artifacts/error_classifier.json` on startup. The frontend files are served
from `frontend/`. Stop the server with `Ctrl+C`.

The app binds to `127.0.0.1` by default. To choose a different local port, set
`WEB_VALIDATOR_PORT` before starting it. To bind a different interface, set
`WEB_VALIDATOR_HOST` explicitly.

## Browser workflow

1. Choose an HTML, CSS, or JavaScript tab and paste source code. The tabs retain
   their contents while you switch between them.
2. Optionally load a valid or intentionally broken example.
3. Choose how many ML categories to rank (1–5), then select **Run analysis**.
4. Review parser diagnostics, semantic checks for all three languages, and ML
   category rankings in separate sections.
5. Open **Model lab** to review held-out scores, language-level results,
   category F1, the token-only baseline, and the dataset split.
6. Use **Export** to save the request and full analysis response for a
   report appendix.

The app parses source as text and never executes submitted code. The server
limits each request body to 256 KB.

## API contract

### `GET /api/health`

Returns HTTP 200 when the server is ready and the model loaded. It also returns
the model feature mode and held-out synthetic evaluation summary:

```json
{
  "status": "ok",
  "service": "web-code-validator",
  "model": "multinomial-naive-bayes",
  "feature_mode": "token_parser",
  "benchmark": {
    "status": "available",
    "dataset": "synthetic_holdout",
    "test_examples": 459,
    "training_split_examples": 1773,
    "validation_examples": 432,
    "training_examples": 2205,
    "accuracy": 0.9325,
    "macro_precision": 0.9548,
    "macro_recall": 0.9338,
    "macro_f1": 0.9353,
    "feature_mode": "token_parser",
    "smoothing_alpha": 0.25,
    "dataset_splits": {"train": 1773, "validation": 432, "test": 459},
    "reference_baseline": {
      "algorithm": "Token-only Multinomial Naive Bayes",
      "test_examples": 459,
      "accuracy": 0.7233,
      "macro_f1": 0.7309
    },
    "by_language": {
      "html": {"examples": 153, "accuracy": 1.0, "macro_f1": 1.0},
      "css": {"examples": 153, "accuracy": 0.9542, "macro_f1": 0.9555},
      "javascript": {"examples": 153, "accuracy": 0.8431, "macro_f1": 0.8503}
    }
  }
}
```

### `POST /api/analyze`

Send `Content-Type: application/json`. `html`, `css`, and `javascript` are
optional strings; pass at least one non-empty source. `top_k` is optional and
must be a whole number from 1 through 5 (default: 3).

```json
{
  "html": "<main><h1>Hello</main>",
  "css": ".card { color red; }",
  "javascript": "const answer = ;",
  "top_k": 3
}
```

On success, the response follows the `ErrorAnalyzer.analyze()` format described
in the [ML model guide](ml-model.md), with semantic diagnostics for all three
languages and a model benchmark summary. It includes:

- `deterministic_diagnostics`: parser availability and reproducible findings,
  including parser name, code, message, and source location where available.
- `predictions`: model-ranked error categories with confidence scores and
  `is_confirmed: false`.
- `semantic_diagnostics.html`: duplicate IDs, missing image alt attributes,
  and unresolved label, same-page fragment-link, and ARIA references.
- `semantic_diagnostics.css`: custom-property (`var(--name)`) references that
  lack a definition or fallback in the submitted stylesheet.
- `semantic_diagnostics.javascript`: undeclared identifiers that cannot be
  resolved in the script or known browser/Node.js globals. This is a
  conservative single-file check; syntax errors cause it to skip.
- `model`: classifier information and the confidence limitation note.

The model also includes a `model.benchmark` snapshot loaded from
`ml/artifacts/evaluation.json`. It records 93.25% accuracy and 0.9353 macro-F1
on 459 held-out synthetic examples. This evaluation does not measure
real-world student or repository code.

For example, when the HTML contains a label whose `for` value does not match
any element ID, the additional field looks like this:

```json
{
  "semantic_diagnostics": {
    "html": {
      "status": "available",
      "validator": "html_static_checks",
      "items": [
        {
          "source": "semantic_validator",
          "code": "HTML_LABEL_TARGET_NOT_FOUND",
          "message": "This label refers to id \"email\", but that id was not found in the source.",
          "line": 1,
          "column": 1,
          "severity": "warning",
          "is_model_prediction": false,
          "is_confirmed_semantic_error": false
        }
      ],
      "note": "These static checks are advisory and do not prove browser or accessibility behavior."
    }
  }
}
```

Parser findings and model predictions are independent output fields. The model
uses deterministic parser codes as input features, but its ranked output is
still a suggestion and not a confirmed compiler result. A syntactically clean
snippet is not proof of browser compatibility or runtime correctness.
The semantic checks are intentionally limited. They do not resolve CSS
cascade/external stylesheets, JavaScript project imports/custom runtime globals,
or markup generated dynamically by JavaScript. Semantic findings do not feed
the classifier; the model uses parser diagnostic codes and source tokens from
its synthetic training corpus.

### Error responses

Invalid JSON, non-string source values, a missing source, unsupported request
fields, and invalid `top_k` values return a 4xx status with this shape:

```json
{
  "error": {
    "code": "NO_SOURCE",
    "message": "Enter HTML, CSS, or JavaScript before running the analysis."
  }
}
```

## How the group components connect

The backend creates one `ErrorAnalyzer` at startup, which loads the checked-in
trained model once. Each API request calls `analyze(html=..., css=...,
javascript=..., top_k=...)`. No model internals need to be duplicated in the
frontend or backend. If the ML module's public function or response fields
change, update the adapter in `backend/app.py` and the result renderer in
`frontend/app.js` together.

## Current scope and limitations

- HTML, CSS, and JavaScript syntax are analyzed with html5lib, tinycss2, and
  Esprima respectively.
- HTML semantic checks use Python's standard-library HTML parser to inspect
  IDs, image alt attributes, labels, fragment links, and ARIA references.
- CSS semantic checks find custom properties used with `var()` that have no
  definition or fallback in the submitted stylesheet.
- JavaScript semantic checks use Esprima's AST to report undeclared identifiers
  in one script. Known browser and Node.js globals are allowed; imports and
  project-specific globals are outside this check's scope.
- The ML classifier predicts only the error categories listed in the [model
  guide](ml-model.md), based on a synthetic dataset.
- The project does not repair submitted code, execute JavaScript, validate
  runtime behavior, or check browser-specific styling support.
- Run the service on a trusted local machine. The development server is not
  configured for public deployment.
