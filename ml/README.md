# ML error-category predictor

This component accepts HTML, CSS, and JavaScript source. It returns likely
error-category rankings with Naive Bayes scores and deterministic parser
diagnostics in separate fields. Model predictions are suggestions, not
confirmed compiler errors. The selected classifier uses parser diagnostic
codes as input features and reuses request diagnostics instead of parsing the
same source twice.

See [the ML model guide](../docs/ml-model.md) for the interface, setup, training,
evaluation, and limitations.

## Quick start

Use Python 3.10 or newer. From the repository root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ml/requirements.txt
.\.venv\Scripts\python.exe -m ml.generate_data
.\.venv\Scripts\python.exe -m ml.train
.\.venv\Scripts\python.exe -m ml.evaluate
.\.venv\Scripts\python.exe -m unittest discover -s ml\tests -v
.\.venv\Scripts\python.exe -m ml.demo --top-k 1
```

Calling the venv interpreter directly avoids PowerShell activation-policy
errors and keeps commands in the project environment.

The Naive Bayes algorithm uses the Python standard library. The selected
parser-assisted feature mode and deterministic diagnostics use the pinned
HTML, CSS, and JavaScript parser dependencies.
The generator creates the fixed synthetic corpus with seed `20261025`;
training selects the feature mode and smoothing parameter using only the
validation split, then fits the saved model on training plus validation data.

```python
from ml import ErrorAnalyzer

analyzer = ErrorAnalyzer()
result = analyzer.analyze(
    html="<div>Welcome</div>",
    css=".card { color: red; }",
    javascript="const ready = true;",
)
```

The 2,664-row corpus contains parser-checked grammar-generated examples and the
original hand-authored examples. It is synthetic data, not real-world
repository code. It includes complete HTML documents as well as the original
HTML fragments. The test templates are held out by family, and the model guide
reports metrics separately with the limitations of this evaluation.

`python -m ml.demo --top-k 1` starts an interactive local test. Paste each
language's source and type `END` on its own line. Pressing `END` without source
skips that language. The command prints the predictions and parser diagnostics
as JSON; it does not start a server or require the frontend.
