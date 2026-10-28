# ML-Based HTML-CSS-JavaScript Compiler

An intelligent web code validation project with an interactive frontend, a
Python API, deterministic HTML/CSS/JavaScript parser diagnostics, focused HTML
semantic checks, and an ML model that ranks likely error categories.

## Run the project

Use Python 3.10 or newer. From the project root in PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ml/requirements.txt
.\.venv\Scripts\python.exe -m backend
```

Calling the environment's Python directly avoids PowerShell activation-policy
errors and keeps the project dependencies inside `.venv`.

Open **http://127.0.0.1:8000** in your browser. The server loads the saved model
from `ml/artifacts/error_classifier.json` and serves the frontend and API on the
same local address. Stop the server with `Ctrl+C`.

## Project components

- `frontend/` — responsive code workbench, HTML/CSS/JavaScript findings, and
  a model lab with held-out evaluation and category metrics.
- `backend/` — local HTTP server and JSON API that calls the analyzer.
- `backend/semantic.py` and `backend/javascript_semantic.py` — focused HTML,
  CSS, and JavaScript semantic checks.
- `ml/` — trained Naive Bayes model, training data, parser diagnostics, and
  evaluation code.
- `docs/` — API guide, setup steps, model behavior, and project limitations.

## API

`POST /api/analyze` accepts a JSON object with any combination of `html`,
`css`, and `javascript` strings, plus optional `top_k` (1–5). The response
keeps parser diagnostics, semantic warnings, and ML predictions in separate
fields. The page can export a JSON analysis report.
`GET /api/health` reports whether the local service is running.

See [the web app and API guide](docs/web-app.md) for request examples and the
full response contract. See the [submission guide](docs/submission-guide.md) for
the architecture, evaluation, test plan, demo steps, and viva notes. See [the ML
model guide](docs/ml-model.md) for training, evaluation, categories, and data
limitations.

If sharing the project, start with the [friend setup and report guide](FRIEND_SETUP_AND_REPORT_GUIDE.md).

## Run the checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s ml\tests -v
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
```

## Important model limitation

The classifier was trained and evaluated on synthetic examples. Its test
accuracy and macro-F1 are documented in the app and report, but they do not
estimate real-world accuracy. Ranking scores are not calibrated probabilities,
and predictions are suggestions, not confirmed compiler errors. The semantic
checks are conservative static checks. Submitted source is parsed as text; the
project does not execute it.

