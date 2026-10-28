"""Generate a reproducible, parser-checked synthetic code corpus."""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path

from .diagnostics import diagnose_source


DATA_DIR = Path(__file__).parent / "data"
DEFAULT_OUTPUT_PATH = DATA_DIR / "grammar_examples.jsonl"
HAND_AUTHORED_PATH = DATA_DIR / "synthetic_examples.jsonl"
SEED = 20261025
VARIANTS_PER_TEMPLATE = 12

WORDS = (
    "card", "panel", "menu", "profile", "gallery", "notice", "feature",
    "toolbar", "status", "summary", "account", "archive", "result",
    "active", "compact", "primary", "search", "catalog", "details",
    "message", "section", "dialog", "header", "footer",
)
TEXTS = (
    "Welcome", "Save changes", "Open menu", "Recent items", "Profile",
    "Search results", "More information", "Continue", "Selected item",
    "Account details", "Choose an option", "Page title", "New message",
    "Project status", "View gallery", "Contact support", "Updated record",
    "Feature list", "Navigation link", "Current selection", "Read summary",
    "Primary action", "Archive entry", "Search panel",
)
COLORS = ("#123456", "#345678", "#456789", "#56789a", "#6789ab", "#789abc")
NUMBERS = (2, 4, 8, 12, 16, 24, 32, 48, 64, 80, 96)


HTML_TEMPLATES = (
    '<div class="{word}">{text}</div>',
    '<section id="{word}"><h2>{text}</h2><p>{text2}</p></section>',
    '<ul class="{word}"><li>{text}</li><li>{text2}</li></ul>',
    '<article><header><h2>{text}</h2></header><p>{text2}</p></article>',
    '<form action="/{word}" method="post"><label>{text}<input name="{word2}"></label><button>{text2}</button></form>',
    '<nav><a href="/{word}">{text}</a><a href="/{word2}">{text2}</a></nav>',
    '<figure><img src="{word}.png" alt="{text}"><figcaption>{text2}</figcaption></figure>',
    '<details><summary>{text}</summary><p>{text2}</p></details>',
    '<table><thead><tr><th>{text}</th><th>{text2}</th></tr></thead><tbody><tr><td>{word}</td><td>{word2}</td></tr></tbody></table>',
    '<main><aside class="{word}">{text}</aside><section><h1>{text2}</h1></section></main>',
    '<select name="{word}"><option value="{word2}">{text}</option><option value="{word3}">{text2}</option></select>',
    '<ol><li>{text}</li><li>{text2}</li><li>{word}</li></ol>',
    '<header><h1>{text}</h1><p>{text2}</p></header>',
    '<footer><a href="mailto:{word}@example.test">{text}</a></footer>',
    '<div id="{word}"><span>{text}</span><strong>{text2}</strong></div>',
    '<section><blockquote><p>{text}</p></blockquote><cite>{text2}</cite></section>',
    '<progress max="100" value="{number}">{number}%</progress>',
    '<p class="{word}">{text} <em>{text2}</em></p>',
)

CSS_TEMPLATES = (
    '.card-{word} {{ color: {color}; padding: {number}px; }}',
    '#item-{word} {{ margin: {number}px; border: 1px solid {color}; }}',
    '.button-{word}:hover {{ background-color: {color}; cursor: pointer; }}',
    '.layout-{word} > .main {{ display: flex; gap: {number}px; }}',
    '@media (min-width: {breakpoint}px) {{ .panel-{word} {{ width: {number}%; }} }}',
    '.text-{word} {{ font-size: {number}px; line-height: 1.4; }}',
    '.grid-{word} {{ display: grid; grid-template-columns: repeat(2, 1fr); }}',
    '.image-{word} {{ background-image: url("{word}.png"); background-size: cover; }}',
    '.box-{word} {{ border-radius: {number}px; box-shadow: 0 2px 4px #333; }}',
    '.list-{word} li:first-child {{ color: {color}; }}',
    '.nav-{word} a[aria-current="page"] {{ text-decoration: none; }}',
    '@supports (display: grid) {{ .cards-{word} {{ display: grid; }} }}',
    '@keyframes {word} {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}',
    '.theme-{word} {{ --accent: {color}; color: var(--accent); }}',
    'input[type="text"].field-{word} {{ outline: 2px solid {color}; }}',
    '.container-{word} {{ max-width: {number}px; margin: 0 auto; }}',
    '.card-{word}::before {{ content: "{text}"; display: block; }}',
    'html[data-theme="{word}"] .title {{ color: {color}; }}',
)

JAVASCRIPT_TEMPLATES = (
    'const total = {number} + {number2}; return total;',
    'const items = ["{word}", "{word2}"]; return items.length;',
    'const record = {{ name: "{word}", count: {number} }}; return record.name;',
    'if ({number} > {number2}) {{ console.log("{text}"); }} else {{ console.log("{text2}"); }} return {number};',
    'let total = 0; for (let index = 0; index < {number}; index++) {{ total += index; }} return total;',
    'const handler = (event) => {{ event.preventDefault(); return "{text}"; }}; return handler;',
    'return [{number}, {number2}].map((value) => value * 2);',
    'try {{ throw new Error("{text}"); }} catch (error) {{ console.log(error.message); }} return true;',
    'const normalize = function(value) {{ return value.trim(); }}; return normalize("{word}");',
    'const output = `Hello {word}`; return output;',
    'let state = {{ open: true, count: {number} }}; if (state.open) {{ state.count += 1; }} return state.count;',
    'switch ({number}) {{ case 1: return "{text}"; default: return "{text2}"; }}',
    'class View {{ render() {{ return "{text}"; }} }} return new View().render();',
    'const found = ["{word}", "{word2}"].find((value) => value.length > 2); return found;',
    'const options = {{ title: "{text}", active: true }}; return options.active;',
    'const square = (value) => value * value; return square({number});',
    'const linked = Object.assign({{}}, {{ label: "{word}" }}); return linked.label;',
    'const message = String({number}) + "{text}"; return message;',
)

LABELS = {
    "html": ("html_unclosed_tag", "html_unexpected_end_tag", "html_duplicate_attribute", "no_likely_error"),
    "css": ("css_missing_colon", "css_unclosed_block", "css_unterminated_string", "no_likely_error"),
    "javascript": ("javascript_unclosed_delimiter", "javascript_unterminated_string", "javascript_unexpected_token", "no_likely_error"),
}


def _values(rng: random.Random) -> dict[str, object]:
    words = rng.sample(WORDS, 3)
    texts = rng.sample(TEXTS, 2)
    return {
        "word": words[0],
        "word2": words[1],
        "word3": words[2],
        "text": texts[0],
        "text2": texts[1],
        "number": rng.choice(NUMBERS),
        "number2": rng.choice(NUMBERS),
        "breakpoint": rng.choice((480, 640, 768, 960, 1024, 1280)),
        "color": rng.choice(COLORS),
    }


def _render_template(language: str, template_id: int, values: dict[str, object]) -> str:
    templates = {
        "html": HTML_TEMPLATES,
        "css": CSS_TEMPLATES,
        "javascript": JAVASCRIPT_TEMPLATES,
    }[language]
    body = templates[template_id].format(**values)
    if language == "css":
        note = f'.generated-{values["word"]} {{ --note: "{values["text"]}"; }}'
        return f"{body}\n{note}"
    if language == "javascript":
        return (
            f"function sample_{template_id}() {{\n  {body}\n"
            f'  const __ml_message__ = "{values["text"]}";\n}}'
        )
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        f'<title>{values["text"]}</title>\n'
        f'</head>\n<body>\n<div class="ml-generated">{body}</div>\n</body>\n</html>'
    )


def _mutate(language: str, label: str, source: str) -> str:
    if label == "no_likely_error":
        return source
    if label == "html_unclosed_tag":
        body_close = source.lower().rfind("</body>")
        content_end = body_close if body_close >= 0 else len(source)
        tags = list(
            re.finditer(
                r"</[A-Za-z][A-Za-z0-9:-]*\s*>", source[:content_end]
            )
        )
        if not tags:
            raise ValueError("HTML template has no closing tag to remove")
        match = tags[-1]
        return source[: match.start()] + source[match.end() :]
    if label == "html_unexpected_end_tag":
        return f"{source}</ml-orphan>"
    if label == "html_duplicate_attribute":
        match = re.search(r"<[A-Za-z][^>]*>", source)
        if match is None:
            raise ValueError("HTML template has no start tag")
        tag = match.group(0)
        tag = tag[:-1] + ' data-ml-duplicate="first" data-ml-duplicate="second">'
        return source[: match.start()] + tag + source[match.end() :]
    if label == "css_missing_colon":
        changed, count = re.subn(
            r"([\{;]\s*)([A-Za-z-]+)\s*:", r"\1\2 ", source, count=1
        )
        if count != 1:
            raise ValueError("CSS template has no declaration colon to remove")
        return changed
    if label == "css_unclosed_block":
        position = source.rfind("}")
        if position < 0:
            raise ValueError("CSS template has no closing brace to remove")
        return source[:position] + source[position + 1 :]
    if label == "css_unterminated_string":
        # The deterministic note declaration is present in every CSS example.
        note_value = re.search(r'(--note:\s*")([^"]*)(")', source)
        if note_value is None:
            raise ValueError("CSS template has no note string to truncate")
        return source[: note_value.end(2)] + source[note_value.end(3) :]
    if label == "javascript_unclosed_delimiter":
        position = source.rfind("}")
        if position < 0:
            raise ValueError("JavaScript template has no closing function brace")
        return source[:position] + source[position + 1 :]
    if label == "javascript_unterminated_string":
        match = re.search(r'const __ml_message__ = "([^"]*)";', source)
        if match is None:
            raise ValueError("JavaScript template has no message string to truncate")
        return source[: match.end(1)] + source[match.end(1) + 1 :]
    if label == "javascript_unexpected_token":
        position = source.rfind("}")
        if position < 0:
            raise ValueError("JavaScript template has no closing function brace")
        return source[:position] + "  const __ml_invalid__ = ;\n" + source[position:]
    raise ValueError(f"unsupported generated label: {language}:{label}")


def _validate_example(language: str, label: str, source: str) -> None:
    diagnostic = diagnose_source(language, source)
    codes = [str(item.get("code", "")) for item in diagnostic["items"]]
    if label == "no_likely_error":
        if codes:
            raise ValueError(f"valid {language} example produced diagnostics: {source!r} {codes}")
        return

    expected = {
        "html_unexpected_end_tag": "UNEXPECTED_END_TAG",
        "html_duplicate_attribute": "DUPLICATE_ATTRIBUTE",
        "css_missing_colon": "CSS_PARSE_INVALID",
        "css_unclosed_block": "CSS_UNCLOSED_BLOCK",
        "css_unterminated_string": "CSS_UNTERMINATED_STRING",
        "javascript_unclosed_delimiter": "JAVASCRIPT_UNCLOSED_DELIMITER",
        "javascript_unterminated_string": "JAVASCRIPT_UNTERMINATED_STRING",
        "javascript_unexpected_token": "JAVASCRIPT_UNEXPECTED_TOKEN",
    }.get(label)
    if label == "html_unclosed_tag":
        if not any("EOF" in code or "EXPECTED" in code for code in codes):
            raise ValueError(f"expected an HTML end-of-input diagnostic for {label}: {source!r} {codes}")
        return
    if expected is not None:
        if not any(expected in code for code in codes):
            raise ValueError(f"expected {expected} for {label}: {source!r} {codes}")
        return

    if language == "javascript" and expected not in codes:
        raise ValueError(
            f"expected {expected} for {label}: {source!r} {codes}"
        )


def generate_examples(seed: int = SEED, variants_per_template: int = VARIANTS_PER_TEMPLATE) -> list[dict[str, str]]:
    if variants_per_template < 1:
        raise ValueError("variants_per_template must be positive")
    examples: list[dict[str, str]] = []
    templates_by_language = {
        "html": HTML_TEMPLATES,
        "css": CSS_TEMPLATES,
        "javascript": JAVASCRIPT_TEMPLATES,
    }
    for language_index, (language, templates) in enumerate(templates_by_language.items()):
        if len(templates) != 18:
            raise ValueError(f"expected 18 {language} template families")
        order = list(range(len(templates)))
        random.Random(seed + language_index).shuffle(order)
        split_by_family = {
            family: ("train" if position < 12 else "validation" if position < 15 else "test")
            for position, family in enumerate(order)
        }
        for family_index in range(len(templates)):
            for variant in range(variants_per_template):
                rng = random.Random(seed + 1009 * language_index + 97 * family_index + variant)
                valid_source = _render_template(language, family_index, _values(rng))
                for label in LABELS[language]:
                    source = _mutate(language, label, valid_source)
                    _validate_example(language, label, source)
                    examples.append(
                        {
                            "language": language,
                            "source": source,
                            "label": label,
                            "split": split_by_family[family_index],
                            "origin": "grammar_generated_synthetic",
                            "group_id": f"{language}:template_{family_index:02d}",
                        }
                    )

    # Preserve the original manually authored examples as a separate source.
    for line_number, line in enumerate(HAND_AUTHORED_PATH.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        row["group_id"] = f"hand_authored:{line_number}"
        examples.append(row)

    examples.sort(
        key=lambda row: (
            row["language"], row["split"], row["group_id"], row["label"], row["source"]
        )
    )
    return examples


def write_dataset(path: str | Path = DEFAULT_OUTPUT_PATH, seed: int = SEED) -> dict[str, object]:
    examples = generate_examples(seed=seed)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(example, sort_keys=True) + "\n" for example in examples),
        encoding="utf-8",
    )
    counts = Counter(example["split"] for example in examples)
    return {"output_path": str(output), "examples": len(examples), "split_counts": dict(sorted(counts.items())), "seed": seed}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    print(json.dumps(write_dataset(args.output, args.seed), indent=2))


if __name__ == "__main__":
    main()
