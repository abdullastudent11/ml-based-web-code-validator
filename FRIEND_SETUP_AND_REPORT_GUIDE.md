# Friend Setup, Demo, and Report Guide

This guide explains how to extract, run, demonstrate, test, and write a report
for **ML-Based HTML-CSS-JavaScript Compiler for Intelligent Web Code Validation**.

## 1. Extract the project

1. Extract `cd-project-ml-model-share.zip` to a folder on the laptop.
2. In Visual Studio Code, choose **File → Open Folder** and open the extracted
   `cd-project-ml-model` folder.
3. Open **Terminal → New Terminal**. Make sure the terminal is at the project
   root: it should contain `backend`, `frontend`, and `ml` folders.

Python 3.10 or later is required. Python 3.12 was used to verify this project.

## 2. Install and start (Windows PowerShell)

Run these commands from the project root:

```powershell
py -3 --version
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r ml\requirements.txt
.\.venv\Scripts\python.exe -m backend
```

The first installation needs an internet connection to download the listed
Python packages. This project does not require activating the virtual
environment; calling its Python directly also avoids PowerShell's script
activation-policy error.

When the terminal says the service is ready, open **http://127.0.0.1:8000/** in
a browser. Keep the terminal open while using the site. Stop the server with
**Ctrl+C**.

If port 8000 is already in use, stop the other copy of this project first. Or
start this copy on port 8001:

```powershell
$env:WEB_VALIDATOR_PORT = "8001"
.\.venv\Scripts\python.exe -m backend
```

Then open **http://127.0.0.1:8001/**.

## 3. Demo the website

1. In **Code workbench**, load **Clean**, then click **Run analysis**. The
   report should show all three languages checked with no parser or semantic
   findings. The ML still returns ranked categories as a prediction exercise.
2. Load **Semantic**, then run it. Review the HTML missing-alt, duplicate-ID,
   and unresolved-reference warnings; the CSS undefined custom property and
   parser finding; and the JavaScript undeclared-identifier warning.
3. Load **Syntax**, then run it. Review the parser findings for malformed HTML,
   CSS, and JavaScript. JavaScript semantic checks are skipped if parsing fails.
4. Change **ML rankings** to Top 1 through Top 5 and run again. The classifier
   has four known categories per language, so Top 5 returns the four available
   categories.
5. Open **Model lab** to see the held-out benchmark, comparison baseline,
   train/validation/test split, language results, and category-level F1.
6. Use **Export** to download a JSON copy of the input and analysis response.

The application parses submitted code as text; it does not execute it. Model
scores are rankings, not calibrated probabilities or confirmed errors.

## 4. Run the automated checks

Open a second terminal at the project root and run:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s ml\tests -v
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
```

The verified project currently has 13 ML tests and 12 backend/semantic tests.
Both suites passed during packaging. Capture the actual test output from the
friend's laptop if the report requires machine-specific evidence.

## 5. Report outline

Use `docs/submission-guide.md`, `docs/ml-model.md`, and `docs/web-app.md` as the
technical source material. A clear BTech-level report can use this structure:

1. **Title page** — project title, student names, roll numbers, department,
   college, guide, and submission date.
2. **Abstract and keywords** — summarize the validation problem, approach, and
   measured synthetic-test result in a short paragraph.
3. **Problem statement and objectives** — explain why web code benefits from
   syntax, semantic, and error-category analysis.
4. **Background / existing approach** — describe conventional parser-based
   validation and the limits this project addresses. Cite any outside sources
   actually consulted.
5. **Proposed system and architecture** — include the architecture diagram in
   `docs/submission-guide.md` and explain the browser, Python API, parsers,
   semantic checks, and classifier.
6. **Methodology and implementation** — document the HTML5, CSS, and
   JavaScript parsers; static checks; feature representation; Naive Bayes
   classifier; top-k output; and JSON API.
7. **Results and discussion** — report the held-out metrics below, explain the
   token-only comparison, and discuss the weaker JavaScript result.
8. **Testing and screenshots** — include the automated test results and
   screenshots of the clean, semantic, syntax, and Model Lab screens.
9. **Limitations and future work** — clearly state that the dataset is
   synthetic, scores are uncalibrated rankings, and checks do not prove browser
   or runtime correctness. Discuss real-code data, score calibration, and
   broader project-aware checks as future work.
10. **Conclusion and references** — summarize what was implemented and list
    sources actually used.

### Evaluation figures to report accurately

The checked-in evaluation uses **459 held-out synthetic examples**. Its results
are:

| Measure | Parser-assisted model | Token-only reference |
| --- | ---: | ---: |
| Accuracy | 93.25% | 72.33% |
| Macro precision | 95.48% | 74.61% |
| Macro recall | 93.38% | 72.86% |
| Macro F1 | 93.53% | 73.09% |

| Language | Test examples | Accuracy | Macro F1 |
| --- | ---: | ---: | ---: |
| HTML | 153 | 100.00% | 100.00% |
| CSS | 153 | 95.42% | 95.55% |
| JavaScript | 153 | 84.31% | 85.03% |

The full dataset split is 1,773 training, 432 validation, and 459 test examples.
These are generated examples, so **do not describe these values as expected
accuracy on real-world or student-written code**.

## 6. Suggested screenshots

Capture screenshots from the running browser and label them in the report:

- Figure 1 — Code workbench with the three source tabs.
- Figure 2 — Clean sample analysis.
- Figure 3 — Semantic warnings across HTML, CSS, and JavaScript.
- Figure 4 — Syntax diagnostics and ML category rankings.
- Figure 5 — Model Lab with overall and per-language evaluation metrics.
- Figure 6 — Passing ML and backend test-suite output.

Avoid including personal desktop notifications or unrelated windows in the
screenshots.
