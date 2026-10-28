const languages = ["html", "css", "javascript"];
const languageNames = { html: "HTML", css: "CSS", javascript: "JavaScript" };
const languageChips = { html: "HT", css: "CS", javascript: "JS" };
const exampleSources = {
  valid: {
    html: "<!DOCTYPE html>\n<html>\n<head>\n  <title>Starter page</title>\n</head>\n<body>\n  <main class=\"card\">\n    <h1>Hello, web</h1>\n    <p>Your code is ready to inspect.</p>\n  </main>\n</body>\n</html>",
    css: "body {\n  font-family: sans-serif;\n  color: #19342e;\n}\n\n.card {\n  padding: 1.5rem;\n  border-radius: 12px;\n}",
    javascript: "const heading = document.querySelector(\"h1\");\n\nif (heading) {\n  heading.textContent = \"Hello, web\";\n}"
  },
  semantic: {
    html: "<!doctype html>\n<html lang=\"en\">\n  <body>\n    <label for=\"missing-email\">Email</label>\n    <img src=\"avatar.png\">\n    <a href=\"#profile\">Profile</a>\n    <p id=\"duplicate\">First</p>\n    <p id=\"duplicate\">Second</p>\n    <div aria-labelledby=\"missing-title\">Details</div>\n  </body>\n</html>",
    css: ".card {\n  color: var(--missing-color);\n  background: var(--brand, teal);\n  color red;\n}",
    javascript: "function greet(user) {\n  console.log(welcomeMessage, user.name);\n}\n\ngreet(\"Ada\");"
  },
  syntax: {
    html: "<main>\n  <h1 class=\"title\">Welcome\n  <p>Hello, web!</p>\n</main>",
    css: ".card {\n  color red;\n  padding: 1rem;\n",
    javascript: "const message = \"hello;\n\nfunction greet() {\n  console.log(message);"
  }
};

const textarea = document.querySelector("#code-input");
const lineNumbers = document.querySelector("#line-numbers");
const editor = document.querySelector("#source-editor");
const analyzeButton = document.querySelector("#analyze-button");
const analyzeLabel = document.querySelector("#analyze-label");
const resultsContent = document.querySelector("#results-content");
const resultSummary = document.querySelector("#result-summary");
const editorCount = document.querySelector("#editor-count");
const editorLanguage = document.querySelector("#editor-language");
const exportButton = document.querySelector("#export-report");
const editorStatus = document.querySelector(".editor-state");
const serviceLabel = document.querySelector("#service-label");

let activeLanguage = "html";
let latestReport = null;

function markInputsChanged() {
  if (!latestReport) return;
  exportButton.disabled = true;
  resultSummary.textContent = "Source changed · analyze again";
  editorStatus.replaceChildren(createElement("span", "state-dot warning-dot"), document.createTextNode(" Source changed"));
}

function updateEditorMeta() {
  const lines = textarea.value.split("\n").length;
  const characters = textarea.value.length;
  lineNumbers.textContent = Array.from({ length: lines }, (_, index) => index + 1).join("\n");
  editorCount.textContent = `${lines} ${lines === 1 ? "line" : "lines"} · ${characters} ${characters === 1 ? "character" : "characters"}`;
}

function setLanguage(language, focus = false) {
  activeLanguage = language;
  document.querySelectorAll(".language-tab").forEach((tab) => {
    const selected = tab.dataset.language === language;
    tab.classList.toggle("is-active", selected);
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
  const tab = document.querySelector(`[data-language="${language}"]`);
  editor.setAttribute("aria-labelledby", tab.id);
  textarea.setAttribute("aria-label", `${languageNames[language]} source code`);
  editorLanguage.textContent = languageNames[language];
  updateEditorMeta();
  if (focus) textarea.focus();
}

function fillExamples(kind) {
  languages.forEach((language) => {
    const sample = exampleSources[kind][language];
    if (language === activeLanguage) textarea.value = sample;
    else sessionStorage.setItem(`webcode-${language}`, sample);
  });
  sessionStorage.setItem(`webcode-${activeLanguage}`, textarea.value);
  updateEditorMeta();
  markInputsChanged();
  textarea.focus();
}

function clearSources() {
  textarea.value = "";
  languages.forEach((language) => sessionStorage.removeItem(`webcode-${language}`));
  updateEditorMeta();
  markInputsChanged();
  textarea.focus();
}

function titleCaseCategory(category) {
  const shortName = String(category).split(":").pop();
  if (shortName === "no_likely_error") return "No likely parser error";
  const words = shortName.split("_");
  const prefix = { html: "HTML", css: "CSS", javascript: "JavaScript" }[words[0]];
  return words.map((word, index) => index === 0 && prefix ? prefix : word.replace(/^\w/, (letter) => letter.toUpperCase())).join(" ");
}

function createElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function renderFinding(finding) {
  const item = createElement("li", "finding-item");
  item.append(createElement("p", "finding-message", finding.message || finding.code || "Parser finding"));
  const location = finding.line ? `Line ${finding.line}${finding.column ? `, column ${finding.column}` : ""}` : "Location unavailable";
  item.append(createElement("p", "finding-meta", `${finding.code || "PARSER_FINDING"} · ${location}`));
  return item;
}

function renderSemanticSection(language, diagnostics, body) {
  body.append(createElement("div", "prediction-divider"));
  body.append(createElement("p", "result-subhead", `${languageNames[language]} semantic checks`));
  const items = Array.isArray(diagnostics?.items) ? diagnostics.items : [];
  if (diagnostics?.status === "available" && items.length) {
    const list = createElement("ul", "finding-list semantic-list");
    items.forEach((finding) => list.append(renderFinding(finding)));
    body.append(list);
  } else if (diagnostics?.status === "skipped_syntax_error") {
    body.append(createElement("p", "unavailable-note", diagnostics.note || "Fix the syntax finding before running semantic checks."));
  } else if (diagnostics?.status === "unavailable") {
    body.append(createElement("p", "unavailable-note", diagnostics.reason || "Semantic checks are unavailable."));
  } else if (diagnostics?.status === "not_provided" || diagnostics?.status === "empty") {
    body.append(createElement("p", "no-finding", `Enter ${languageNames[language]} to run these checks.`));
  } else {
    const okay = createElement("p", "no-finding");
    okay.append(createElement("span", "checkmark", "✓"));
    okay.append(document.createTextNode("No issues found by the available static checks."));
    body.append(okay);
  }
  if (diagnostics?.note && diagnostics.status !== "skipped_syntax_error") body.append(createElement("p", "semantic-note", diagnostics.note));
}

function renderLanguageResult(language, diagnostics, predictions, semanticDiagnostics) {
  const card = createElement("article", "language-result");
  const items = Array.isArray(diagnostics?.items) ? diagnostics.items : [];
  const status = diagnostics?.status || "unknown";
  const header = createElement("div", "language-result-header");
  const title = createElement("h3", "language-result-title");
  title.append(createElement("span", "lang-chip", languageChips[language]));
  title.append(document.createTextNode(languageNames[language]));
  header.append(title);

  const statusLabel = status === "available" ? (items.length ? `${items.length} finding${items.length === 1 ? "" : "s"}` : "No findings") : status === "not_provided" ? "Not provided" : status === "empty" ? "Empty" : "Parser unavailable";
  const statusClass = status === "unavailable" ? "parser-status unavailable" : items.length ? "parser-status has-findings" : "parser-status";
  header.append(createElement("span", statusClass, statusLabel));
  card.append(header);

  const body = createElement("div", "language-result-body");
  body.append(createElement("p", "result-subhead", "Parser diagnostics"));
  if (status === "unavailable") {
    body.append(createElement("p", "unavailable-note", diagnostics.reason || "Install the parser dependencies to enable deterministic diagnostics."));
  } else if (items.length) {
    const findings = createElement("ul", "finding-list");
    items.forEach((finding) => findings.append(renderFinding(finding)));
    body.append(findings);
  } else if (status === "not_provided" || status === "empty") {
    body.append(createElement("p", "no-finding", status === "empty" ? "No source was entered for this language." : "No source was provided for this language."));
  } else {
    const okay = createElement("p", "no-finding");
    okay.append(createElement("span", "checkmark", "✓"));
    okay.append(document.createTextNode("No parser findings returned."));
    body.append(okay);
  }

  if (semanticDiagnostics) renderSemanticSection(language, semanticDiagnostics, body);

  body.append(createElement("div", "prediction-divider"));
  body.append(createElement("p", "result-subhead", "ML category ranking"));
  if (Array.isArray(predictions) && predictions.length) {
    const list = createElement("ol", "prediction-list");
    predictions.forEach((prediction, index) => {
      const row = createElement("li", "prediction-row");
      const label = createElement("span", "prediction-rank");
      label.append(createElement("span", "rank-number", `0${index + 1}`));
      label.append(document.createTextNode(titleCaseCategory(prediction.category || "unknown")));
      row.append(label);
      const confidence = Number(prediction.confidence);
      const score = createElement("div", "prediction-value");
      const percentage = Number.isFinite(confidence) ? Math.max(0, Math.min(1, confidence)) : 0;
      score.append(createElement("span", "prediction-score", Number.isFinite(confidence) ? `${(percentage * 100).toFixed(1)}%` : "—"));
      const meter = document.createElement("progress");
      meter.className = "score-bar";
      meter.max = 1;
      meter.value = percentage;
      meter.setAttribute("aria-label", `Relative model ranking score ${(percentage * 100).toFixed(1)} percent`);
      score.append(meter);
      row.append(score);
      list.append(row);
    });
    body.append(list);
    body.append(createElement("p", "model-caveat", "Model ranking score · not a calibrated probability"));
  } else {
    body.append(createElement("p", "no-predictions", "Add source code to see the ML ranking."));
  }
  card.append(body);
  return card;
}

function renderResults(result) {
  resultsContent.replaceChildren();
  const group = createElement("div", "results-populated");
  let findingCount = 0;
  let semanticCount = 0;
  let analyzedCount = 0;
  languages.forEach((language) => {
    const diagnostics = result.deterministic_diagnostics?.[language] || { status: "unknown", items: [] };
    const predictions = result.predictions?.[language] || [];
    const semanticDiagnostics = result.semantic_diagnostics?.[language] || null;
    findingCount += Array.isArray(diagnostics.items) ? diagnostics.items.length : 0;
    semanticCount += Array.isArray(semanticDiagnostics?.items) ? semanticDiagnostics.items.length : 0;
    if (predictions.length) analyzedCount += 1;
    group.append(renderLanguageResult(language, diagnostics, predictions, semanticDiagnostics));
  });
  resultsContent.append(group);
  const totalFindings = findingCount + semanticCount;
  resultSummary.textContent = totalFindings ? `${totalFindings} finding${totalFindings === 1 ? "" : "s"}` : `${analyzedCount} language${analyzedCount === 1 ? "" : "s"} checked`;
  renderBenchmark(result.model);
}

function renderBenchmark(modelInfo) {
  if (!modelInfo) return;
  const benchmark = modelInfo.benchmark;
  if (modelInfo.algorithm) {
    const name = modelInfo.algorithm.replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
    document.querySelector("#model-algorithm").textContent = name;
  }
  if (modelInfo.feature_mode) document.querySelector("#model-feature-mode").textContent = modelInfo.feature_mode;
  if (!benchmark || benchmark.status !== "available") {
    ["#model-accuracy", "#model-macro-f1", "#model-precision", "#model-recall"].forEach((selector) => {
      document.querySelector(selector).textContent = "—";
    });
    document.querySelector("#model-test-size").textContent = "Evaluation unavailable";
    document.querySelector("#baseline-comparison").replaceChildren(createElement("p", "loading-note", benchmark?.note || "Evaluation report could not be loaded."));
    document.querySelector("#model-languages").replaceChildren(createElement("p", "loading-note", "Language metrics are unavailable."));
    document.querySelector("#category-results").replaceChildren(createElement("p", "loading-note", "Category metrics are unavailable."));
    return;
  }
  const percentage = (value) => `${(Number(value) * 100).toFixed(2)}%`;
  const metricText = (value) => Number.isFinite(Number(value)) ? percentage(value) : "—";
  document.querySelector("#model-accuracy").textContent = percentage(benchmark.accuracy);
  document.querySelector("#model-macro-f1").textContent = percentage(benchmark.macro_f1);
  document.querySelector("#model-precision").textContent = metricText(benchmark.macro_precision);
  document.querySelector("#model-recall").textContent = metricText(benchmark.macro_recall);
  document.querySelector("#model-test-size").textContent = `${Number(benchmark.training_examples).toLocaleString()} train + validation examples`;
  document.querySelector("#model-alpha").textContent = benchmark.smoothing_alpha ?? "—";
  const selection = benchmark.selected_on_validation;
  document.querySelector("#validation-selection").textContent = selection
    ? `Validation selection · accuracy ${metricText(selection.accuracy)} · macro F1 ${metricText(selection.macro_f1)}`
    : "Validation selection details appear after the local service is restarted.";

  const comparison = document.querySelector("#baseline-comparison");
  comparison.replaceChildren();
  const baseline = benchmark.reference_baseline;
  const models = [
    { label: "Parser-assisted · Accuracy", value: benchmark.accuracy, baseline: false },
    { label: "Token-only · Accuracy", value: baseline?.accuracy, baseline: true },
    { label: "Parser-assisted · Macro F1", value: benchmark.macro_f1, baseline: false },
    { label: "Token-only · Macro F1", value: baseline?.macro_f1, baseline: true }
  ].filter((model) => Number.isFinite(Number(model.value)));
  models.forEach((model) => {
    const row = createElement("div", `compare-row${model.baseline ? " baseline" : ""}`);
    row.append(createElement("span", "compare-name", model.label));
    const track = createElement("div", "compare-track");
    const fill = createElement("div", "compare-fill");
    fill.style.width = `${Math.max(0, Math.min(100, Number(model.value) * 100))}%`;
    track.append(fill);
    row.append(track, createElement("span", "compare-value", percentage(model.value)));
    comparison.append(row);
  });
  if (!baseline) comparison.append(createElement("p", "loading-note", "Baseline comparison details appear after the local service is restarted."));

  const splits = benchmark.dataset_splits || {};
  const splitItems = [
    { key: "train", label: "Train", className: "split-train" },
    { key: "validation", label: "Validation", className: "split-validation" },
    { key: "test", label: "Test", className: "split-test" }
  ];
  const splitTotal = splitItems.reduce((sum, item) => sum + Number(splits[item.key] || 0), 0);
  const splitBar = document.querySelector("#split-bar");
  const splitLegend = document.querySelector("#split-counts");
  splitBar.replaceChildren();
  splitLegend.replaceChildren();
  if (splitTotal) splitItems.forEach((item) => {
    const count = Number(splits[item.key] || 0);
    const segment = createElement("span", `split-segment ${item.className}`);
    segment.style.width = splitTotal ? `${count / splitTotal * 100}%` : "0%";
    segment.title = `${item.label}: ${count.toLocaleString()} examples`;
    splitBar.append(segment);
    const entry = createElement("div", "split-item");
    const label = createElement("span", "split-label");
    label.append(document.createElement("i"), document.createTextNode(item.label));
    entry.append(label, createElement("strong", "", count.toLocaleString()));
    splitLegend.append(entry);
  });
  else splitLegend.append(createElement("p", "loading-note", "Split details appear after the local service is restarted."));

  const languageContainer = document.querySelector("#model-languages");
  const categoryContainer = document.querySelector("#category-results");
  languageContainer.replaceChildren();
  categoryContainer.replaceChildren();
  const languages = Object.entries(benchmark.by_language || {});
  if (!languages.length) {
    languageContainer.append(createElement("p", "loading-note", "Language-level details appear after the local service is restarted."));
    categoryContainer.append(createElement("p", "loading-note", "Category-level details appear after the local service is restarted."));
  }
  languages.forEach(([language, metrics]) => {
    const title = languageNames[language] || language;
    const card = createElement("article", "language-metric-card");
    const heading = createElement("div", "language-metric-heading");
    heading.append(createElement("strong", "", title), createElement("span", "", `${Number(metrics.examples).toLocaleString()} test examples`));
    card.append(heading);
    const values = createElement("div", "language-metric-values");
    [ ["ACCURACY", metrics.accuracy], ["MACRO F1", metrics.macro_f1] ].forEach(([label, value]) => {
      const metric = createElement("div");
      metric.append(createElement("span", "", label), createElement("strong", "", percentage(value)));
      values.append(metric);
    });
    card.append(values);
    const accuracyTrack = createElement("div", "language-accuracy-track");
    const accuracyFill = document.createElement("i");
    accuracyFill.style.width = `${Math.max(0, Math.min(100, Number(metrics.accuracy) * 100))}%`;
    accuracyTrack.append(accuracyFill);
    card.append(accuracyTrack);
    languageContainer.append(card);

    const categoryCard = createElement("article", "category-language");
    categoryCard.append(createElement("h3", "", title));
    (metrics.per_class || []).forEach((entry) => {
      const row = createElement("div", "category-row");
      const rowHead = createElement("div", "category-row-head");
      rowHead.append(createElement("span", "", titleCaseCategory(entry.category)), createElement("span", "", percentage(entry.f1)));
      const track = createElement("div", "category-track");
      const fill = document.createElement("i");
      fill.style.width = `${Math.max(0, Math.min(100, Number(entry.f1) * 100))}%`;
      track.append(fill);
      row.append(rowHead, track, createElement("div", "category-support", `Support · ${Number(entry.support).toLocaleString()}`));
      categoryCard.append(row);
    });
    categoryContainer.append(categoryCard);
  });
}

function exportReport() {
  if (!latestReport) return;
  const blob = new Blob([JSON.stringify(latestReport, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = createElement("a");
  link.href = url;
  link.download = `webcode-analysis-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function renderRequestError(message) {
  resultsContent.replaceChildren();
  const error = createElement("div", "request-error");
  error.setAttribute("role", "alert");
  error.append(createElement("span", "", "!"));
  const copy = document.createElement("div");
  copy.append(createElement("strong", "", "Analysis could not run"));
  copy.append(document.createTextNode(message));
  error.append(copy);
  resultsContent.append(error);
  resultSummary.textContent = "Needs attention";
}

async function analyze() {
  const sources = Object.fromEntries(languages.map((language) => [
    language,
    language === activeLanguage ? textarea.value : sessionStorage.getItem(`webcode-${language}`) || ""
  ]));
  if (!languages.some((language) => sources[language].trim())) {
    renderRequestError("Enter some HTML, CSS, or JavaScript in the editor first.");
    setLanguage(activeLanguage, true);
    return;
  }
  analyzeButton.disabled = true;
  analyzeLabel.textContent = "Analyzing…";
  resultSummary.textContent = "Checking source";
  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...sources, top_k: Number(document.querySelector("#top-k-select").value) })
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload?.error?.message || "The server rejected this request.");
    latestReport = {
      generated_at: new Date().toISOString(),
      sources,
      analysis: payload
    };
    exportButton.disabled = false;
    renderResults(payload);
    editorStatus.replaceChildren(createElement("span", "state-dot"), document.createTextNode(" Analysis complete"));
  } catch (error) {
    renderRequestError(error instanceof TypeError ? "Could not reach the local analysis server. Start the app from the project folder and try again." : error.message);
    editorStatus.replaceChildren(createElement("span", "state-dot warning-dot"), document.createTextNode(" Analysis service unavailable"));
  } finally {
    analyzeButton.disabled = false;
    analyzeLabel.textContent = "Analyze code";
  }
}

document.querySelectorAll(".language-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    sessionStorage.setItem(`webcode-${activeLanguage}`, textarea.value);
    setLanguage(tab.dataset.language, true);
    textarea.value = sessionStorage.getItem(`webcode-${activeLanguage}`) || "";
    updateEditorMeta();
  });
  tab.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const tabs = [...document.querySelectorAll(".language-tab")];
    const index = tabs.indexOf(tab);
    const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    tabs[nextIndex].click();
  });
});

textarea.addEventListener("input", () => {
  sessionStorage.setItem(`webcode-${activeLanguage}`, textarea.value);
  updateEditorMeta();
  markInputsChanged();
});
textarea.addEventListener("scroll", () => { lineNumbers.scrollTop = textarea.scrollTop; });
document.querySelector("#valid-example").addEventListener("click", () => fillExamples("valid"));
document.querySelector("#error-example").addEventListener("click", () => fillExamples("semantic"));
document.querySelector("#syntax-example").addEventListener("click", () => fillExamples("syntax"));
document.querySelector("#clear-editor").addEventListener("click", clearSources);
analyzeButton.addEventListener("click", analyze);
exportButton.addEventListener("click", exportReport);
textarea.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    analyze();
  }
});

if (!sessionStorage.getItem("webcode-initialized")) {
  if (languages.every((language) => sessionStorage.getItem(`webcode-${language}`) === null)) {
    languages.forEach((language) => sessionStorage.setItem(`webcode-${language}`, exampleSources.valid[language]));
  }
  sessionStorage.setItem("webcode-initialized", "true");
}
setLanguage(activeLanguage);
textarea.value = sessionStorage.getItem("webcode-html") || "";
updateEditorMeta();
fetch("/api/health")
  .then((response) => {
    if (!response.ok) throw new Error("The local service is not ready.");
    return response.json();
  })
  .then((health) => {
    renderBenchmark({ algorithm: health.model, feature_mode: health.feature_mode, benchmark: health.benchmark });
    serviceLabel.textContent = "Local service ready";
    serviceLabel.parentElement.classList.remove("is-offline");
    editorStatus.replaceChildren(createElement("span", "state-dot"), document.createTextNode(" Analysis service ready"));
  })
  .catch(() => {
    serviceLabel.textContent = "Local service offline";
    serviceLabel.parentElement.classList.add("is-offline");
    editorStatus.replaceChildren(createElement("span", "state-dot warning-dot"), document.createTextNode(" Start local service to analyze"));
  });

function showView(view, updateAddress = true) {
  const isModel = view === "model";
  document.querySelector("#workbench-view").hidden = isModel;
  document.querySelector("#model-view").hidden = !isModel;
  document.querySelector("#page-crumb").textContent = isModel ? "Model lab" : "Code workbench";
  document.querySelectorAll(".nav-item[data-view]").forEach((button) => {
    const selected = button.dataset.view === (isModel ? "model" : "workbench");
    button.classList.toggle("is-active", selected);
    if (selected) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  if (updateAddress) history.replaceState(null, "", isModel ? "#model" : "#workbench");
}

document.querySelectorAll("[data-view]").forEach((button) => {
  button.addEventListener("click", () => showView(button.dataset.view));
});
window.addEventListener("hashchange", () => showView(location.hash === "#model" ? "model" : "workbench", false));
showView(location.hash === "#model" ? "model" : "workbench", false);
