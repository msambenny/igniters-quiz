#!/usr/bin/env python3
"""Igniters youth quiz pipeline: intake -> format -> validate -> build Kahoot payload -> record.

Subcommands
  new       Create the quiz folder (quizzes/YYYY-MM/YYYY-MM-DD-slug), copy the source file, extract raw text.
  validate  Parse formatted.md, check every rule, write quiz.json + validation.md. Exit 1 on errors.
  build     Turn a valid quiz.json into kahoot-payload.json (applies language mode and Kahoot limits).
  record    Save the created Kahoot's id/URL to kahoot.json and the month's index.md.

Only the Python standard library is needed; PDF extraction uses pypdf when it is installed.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
import unicodedata
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUIZZES = Path(os.environ.get("IGNITERS_QUIZZES") or ROOT / "quizzes")
FONTS = ROOT / "fonts"
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
LIMITS = CONFIG["limits"]
DEFAULTS = CONFIG["defaults"]

CHECK = "✅"
KAHOOT_TIMES = (5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240)
TF_HEADING = re.compile(r"^true\s*(?:or|/)\s*false\s*[?:]?\s*", re.I)
MULTI_HEADING = re.compile(r"^multiple[- ]answers?(?:\s+questions?)?\s*[?:]?\s*", re.I)
LETTERS = "ABCDEF"
TAMIL = re.compile(r"[஀-௿]")
# pypdf turns some Tamil fonts into glyph names such as "/ka_uசatraஇtamil"
GARBLED_TAMIL = re.compile(r"/[a-z_]+[஀-௿]*(?:atra|tamil)")
REFERENCE = re.compile(r"\s*\(([1-3]?\s?[A-Z][a-z]+\.?\s*\d+\s*:[^)]*)\)\s*$")


def kahoot_text(text, strip_reference=False):
    """Text as it will appear in Kahoot: reference removed (questions) and bold tags (config)."""
    if strip_reference:
        text = REFERENCE.sub("", text).strip()
    return f"<b>{text}</b>" if DEFAULTS.get("bold") else text


STOPWORDS = set("""a an the and or but of to in on at by for from with into onto as is are was were be been being
has have had do does did not no nor so than that this these those there their them they his her him he she it its
we us our you your who whom whose what which when where why how all any each every some such only own same other
can could should would will shall may might must about after before over under again while during through up down
out off very just also then once here according following included described compared lists order gives true false
select correct answers answer start doing someone person people one two let come able more between chapter chapters""".split())
SECTION_IMAGES = ("ancient scroll", "quill and ink", "old manuscript", "parchment letter", "candle and bible",
                  "stone tablets", "oil lamp", "desert landscape")


def image_query(*texts, words=4, seen=None):
    """Unsplash search for a slide or question: its first few key words, unique within the quiz."""
    keys = []
    for text in texts:
        for word in re.findall(r"[A-Za-z][A-Za-z'-]+", REFERENCE.sub("", text or "")):
            word = word.strip("'-")
            if len(word) > 2 and word.lower() not in STOPWORDS and word.lower() not in (k.lower() for k in keys):
                keys.append(word)
    query = " ".join(keys[:words]) or "bible"
    if seen is not None:
        extra = words
        while query.lower() in seen and extra < len(keys):
            extra += 1
            query = " ".join(keys[:extra])
        seen.add(query.lower())
    return query[:100]


# ---------------------------------------------------------------- helpers

def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "quiz"


def clean(text):
    """Normalise ligatures, quotes and whitespace without touching Tamil."""
    for bad, good in {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
                      "‘": "'", "’": "'", "“": '"', "”": '"',
                      " ": " ", "\t": " "}.items():
        text = text.replace(bad, good)
    return re.sub(r"[ ]{2,}", " ", text).strip()


def quiz_dir(arg):
    path = Path(arg)
    if not path.is_absolute():
        path = (Path.cwd() / path) if (Path.cwd() / path).exists() else QUIZZES / arg
    if not path.is_dir():
        sys.exit(f"Quiz folder not found: {arg}")
    return path


# ---------------------------------------------------------------- new

def extract_text(src):
    suffix = src.suffix.lower()
    if suffix == ".pdf":
        try:
            import pypdf
        except ImportError:
            return None, "pypdf is not installed; read the PDF directly and paste its text into raw.txt."
        reader = pypdf.PdfReader(str(src))
        pages = [f"=== page {i} ===\n{p.extract_text() or ''}" for i, p in enumerate(reader.pages, 1)]
        return "\n".join(pages), None
    if suffix == ".docx":
        with zipfile.ZipFile(src) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"<[^>]+>", "", xml), None
    return src.read_text(encoding="utf-8", errors="replace"), None


def cmd_new(args):
    date = dt.date.fromisoformat(args.date)
    folder = QUIZZES / date.strftime("%Y-%m") / f"{date.isoformat()}-{slugify(args.slug)}"
    if folder.exists() and not args.force:
        sys.exit(f"Already exists: {folder} (use --force to reuse it)")
    (folder / "source").mkdir(parents=True, exist_ok=True)

    notes = []
    if args.source:
        src = Path(args.source).expanduser()
        shutil.copy2(src, folder / "source" / src.name)
        text, problem = extract_text(src)
        if problem:
            notes.append(problem)
        if text is not None:
            (folder / "raw.txt").write_text(text, encoding="utf-8")
            if GARBLED_TAMIL.search(text):
                notes.append("Tamil text came out garbled (font glyph names). Re-read the PDF visually, ask for a "
                             ".docx/text copy, or drop the Tamil lines and say so in the report.")
    print(json.dumps({"folder": str(folder), "raw_text": str(folder / "raw.txt") if (folder / "raw.txt").exists() else None,
                      "notes": notes}, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- validate

def parse(text):
    """Parse formatted.md into (meta, sections, questions, parse_errors)."""
    meta, questions, errors = {}, [], []
    section, current = None, None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = clean(raw)
        if not line:
            continue
        if m := re.match(r"^(title|date|description|time|cover)\s*:\s*(.*)$", line, re.I):
            if current is None:
                meta[m.group(1).lower()] = m.group(2).strip()
                continue
        if m := re.match(r"^#{1,3}\s*(.+)$", line):
            section = m.group(1).strip()
            continue
        if re.match(r"^chapters?\s+\d", line, re.I) and (current is None or current["answers"]):
            section = line  # example-sheet section line, e.g. "Chapters 1, 2"
            continue
        if m := re.match(r"^(\d+)[.)]\s+(.*)$", line):
            current = {"number": int(m.group(1)), "line": lineno, "section": section, "type": "quiz",
                       "time": None, "text": "", "tamil": None, "answers": []}
            rest = m.group(2)
            # Example-sheet headings: "11. True or False?" / "14. Multiple answer questions:"
            if tf := TF_HEADING.match(rest):
                current["type"] = "true_false"
                rest = rest[tf.end():]
            elif multi := MULTI_HEADING.match(rest):
                current["type"] = "multiple_select"
                rest = rest[multi.end():]
            while tag := re.match(r"^\[(tf|multi|time:\s*\d+)\]\s*", rest, re.I):
                value = tag.group(1).lower()
                if value == "tf":
                    current["type"] = "true_false"
                elif value == "multi":
                    current["type"] = "multiple_select"
                else:
                    current["time"] = int(value.split(":")[1])
                rest = rest[tag.end():]
            current["text"] = rest.strip()
            questions.append(current)
            continue
        if current is None:
            errors.append(f"line {lineno}: text before the first question: {line[:60]!r}")
            continue
        if m := re.match(r"^ta\s*:\s*(.+)$", line, re.I):
            current["tamil"] = m.group(1).strip()
            continue
        if m := re.match(r"^([A-F])[.)]\s*(.*)$", line):
            body = m.group(2).strip()
            correct = CHECK in body
            body = body.replace(CHECK, "").strip()
            english, _, tamil = body.partition(" / ")
            current["answers"].append({"letter": m.group(1), "text": body, "english": english.strip(),
                                       "tamil": tamil.strip() or None, "correct": correct})
            continue
        if line == CHECK and current["answers"]:
            current["answers"][-1]["correct"] = True
            continue
        if not current["answers"]:
            if current["text"] and TAMIL.search(line) and not re.search(r"[A-Za-z]{3}", line):
                current["tamil"] = line  # Tamil translation on the line under the question
            else:
                current["text"] = f"{current['text']} {line}".strip()  # wrapped question line
        else:
            errors.append(f"line {lineno}: unexpected line inside Q{current['number']}: {line[:60]!r}")
    return meta, questions, errors


def validate(meta, questions, parse_errors):
    errors, warnings = list(parse_errors), []

    title = meta.get("title", "")
    if not title:
        errors.append("header: `title:` is missing")
    elif len(title) > LIMITS["title_max_chars"]:
        errors.append(f"header: title is {len(title)} chars (max {LIMITS['title_max_chars']})")
    try:
        dt.date.fromisoformat(meta.get("date", ""))
    except ValueError:
        errors.append(f"header: `date:` must be YYYY-MM-DD, got {meta.get('date')!r}")
    if len(meta.get("description", "")) > LIMITS["description_max_chars"]:
        errors.append("header: description is too long")
    if "time" in meta and not meta["time"].isdigit():
        errors.append(f"header: `time:` must be whole seconds, got {meta['time']!r}")

    if not questions:
        errors.append("no questions found")
    if len(questions) > LIMITS["max_questions"]:
        errors.append(f"{len(questions)} questions (max {LIMITS['max_questions']})")

    seen_text = {}
    for expected, q in enumerate(questions, 1):
        tag = f"Q{q['number']}"
        if q["number"] != expected:
            errors.append(f"{tag}: numbering out of order (expected {expected})")
        if not q["text"]:
            errors.append(f"{tag}: question text is empty")
        if GARBLED_TAMIL.search(q["text"] + " ".join(a["text"] for a in q["answers"]) + (q["tamil"] or "")):
            errors.append(f"{tag}: contains garbled Tamil glyph names")
        in_kahoot = len(kahoot_text(q["text"], DEFAULTS["strip_references"]))
        if in_kahoot > LIMITS["question_max_chars"]:
            errors.append(f"{tag}: question is {in_kahoot} chars in Kahoot (max {LIMITS['question_max_chars']}, "
                          "bold tags included); shorten it")
        if TAMIL.search(q["text"]):
            warnings.append(f"{tag}: Tamil inside the English question line; move it to a `ta:` line")
        if not REFERENCE.search(q["text"]):
            warnings.append(f"{tag}: no Bible reference like (Amos 3:7) at the end")
        key = re.sub(r"\W+", " ", q["text"].lower()).strip()
        if key in seen_text:
            warnings.append(f"{tag}: same question text as Q{seen_text[key]}")
        seen_text.setdefault(key, q["number"])

        answers = q["answers"]
        letters = "".join(a["letter"] for a in answers)
        if letters != LETTERS[:len(answers)]:
            errors.append(f"{tag}: answers must be lettered A, B, C… in order (got {letters or 'none'})")
        if not LIMITS["min_answers"] <= len(answers) <= LIMITS["max_answers"]:
            errors.append(f"{tag}: has {len(answers)} answers (allowed {LIMITS['min_answers']}–{LIMITS['max_answers']})")
        for a in answers:
            if not a["text"]:
                errors.append(f"{tag}{a['letter']}: empty answer")
            if len(kahoot_text(a["text"])) > LIMITS["answer_max_chars"]:
                if len(kahoot_text(a["english"])) > LIMITS["answer_max_chars"]:
                    errors.append(f"{tag}{a['letter']}: answer is {len(kahoot_text(a['english']))} chars in Kahoot "
                                  f"(max {LIMITS['answer_max_chars']}, bold tags included)")
                else:
                    warnings.append(f"{tag}{a['letter']}: bilingual answer too long, English only will be used")
        texts = [a["text"].lower() for a in answers]
        if len(set(texts)) != len(texts):
            errors.append(f"{tag}: duplicate answers")

        n_correct = sum(a["correct"] for a in answers)
        if n_correct == 0:
            errors.append(f"{tag}: no answer marked {CHECK}")
        if q["type"] == "true_false":
            if sorted(a["english"].lower() for a in answers) != ["false", "true"]:
                errors.append(f"{tag}: true/false must have exactly the answers True and False")
            if n_correct > 1:
                errors.append(f"{tag}: true/false has more than one correct answer")
        elif q["type"] == "quiz" and n_correct > 1:
            errors.append(f"{tag}: {n_correct} answers marked {CHECK}; add [multi] if that is intended")
        elif q["type"] == "multiple_select" and n_correct < 2:
            warnings.append(f"{tag}: tagged [multi] but only {n_correct} correct answer")
        if q["type"] == "quiz" and sorted(t.strip(". ") for t in texts) == ["false", "true"]:
            warnings.append(f"{tag}: looks like a true/false question; add [tf]")
        if q["time"] is not None and q["time"] not in KAHOOT_TIMES:
            errors.append(f"{tag}: Kahoot time limits are {'/'.join(map(str, KAHOOT_TIMES))}s, got {q['time']}")
    return errors, warnings


def write_report(folder, meta, questions, errors, warnings):
    counts = {}
    for q in questions:
        counts[q["type"]] = counts.get(q["type"], 0) + 1
    lines = [f"# Validation – {meta.get('title', '(no title)')}", "",
             f"- Status: **{'FAILED' if errors else 'PASSED'}**",
             f"- Questions: {len(questions)} ({', '.join(f'{v} {k}' for k, v in counts.items()) or 'none'})",
             f"- Checked: {dt.datetime.now().isoformat(timespec='seconds')}", ""]
    for heading, items in (("Errors (must fix)", errors), ("Warnings (review)", warnings)):
        lines += [f"## {heading}", ""] + ([f"- {i}" for i in items] or ["- none"]) + [""]
    lines += ["## Answer key", "", "| # | Type | Correct | Section |", "|---|---|---|---|"]
    for q in questions:
        correct = ", ".join(f"{a['letter']}) {a['english']}" for a in q["answers"] if a["correct"]) or "—"
        lines.append(f"| {q['number']} | {q['type']} | {correct} | {q['section'] or ''} |")
    (folder / "validation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_validate(args):
    folder = quiz_dir(args.folder)
    source = folder / "formatted.md"
    if not source.exists():
        sys.exit(f"Missing {source}; write the formatted quiz first.")
    meta, questions, parse_errors = parse(source.read_text(encoding="utf-8"))
    errors, warnings = validate(meta, questions, parse_errors)
    sections = list(dict.fromkeys(q["section"] for q in questions if q["section"]))
    (folder / "quiz.json").write_text(json.dumps(
        {"meta": meta, "sections": sections, "questions": questions, "valid": not errors},
        ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(folder, meta, questions, errors, warnings)
    print(json.dumps({"valid": not errors, "questions": len(questions), "errors": errors,
                      "warnings": warnings, "report": str(folder / "validation.md")}, ensure_ascii=False, indent=2))
    sys.exit(1 if errors else 0)


# ---------------------------------------------------------------- build

def cmd_build(args):
    folder = quiz_dir(args.folder)
    data = json.loads((folder / "quiz.json").read_text(encoding="utf-8"))
    if not data.get("valid"):
        sys.exit("quiz.json is not valid; fix formatted.md and run validate again.")
    meta, mode = data["meta"], args.language or DEFAULTS["language_mode"]
    default_time = int(meta.get("time") or DEFAULTS["time_limit_seconds"])
    notes, questions = [], []

    def pick(english, tamil, full, limit, label):
        if mode == "english_only" or not tamil:
            return kahoot_text(english)
        if mode == "tamil_only":
            return kahoot_text(tamil)
        if len(kahoot_text(full)) <= limit:
            return kahoot_text(full)
        notes.append(f"{label}: bilingual text too long, English only")
        return kahoot_text(english)

    # Shape matches the Kahoot! connector's create_or_update_kahoot input: time in ms,
    # true/false as {type, question, correct}, section headings as content slides.
    # The connector requires cover_image_query and an image_query on every item.
    strip = DEFAULTS["strip_references"]
    seen = set()
    section = None
    for q in data["questions"]:
        if args.sections and q["section"] and q["section"] != section:
            section = q["section"]
            theme = SECTION_IMAGES[sum(1 for item in questions if item["type"] == "content") % len(SECTION_IMAGES)]
            questions.append({"type": "content", "title": kahoot_text(section)[:120],
                              "image_query": image_query(section, theme, seen=seen)})
        english = REFERENCE.sub("", q["text"]).strip() if strip else q["text"]
        question = pick(english, q["tamil"], f"{english}\n{q['tamil']}", LIMITS["question_max_chars"], f"Q{q['number']}")
        time_ms = (q["time"] or default_time) * 1000
        correct_text = " ".join(a["english"] for a in q["answers"] if a["correct"])
        image = image_query(q["text"], correct_text, seen=seen)
        if q["type"] == "true_false":
            correct = next(a["english"].lower() == "true" for a in q["answers"] if a["correct"])
            questions.append({"type": "true_false", "question": question, "correct": correct, "time": time_ms,
                              "image_query": image})
            continue
        if q["type"] == "multiple_select":
            notes.append(f"Q{q['number']}: Kahoot has no select-all type; any one marked answer scores")
        choices = [{"answer": pick(a["english"], a["tamil"], a["text"], LIMITS["answer_max_chars"],
                                   f"Q{q['number']}{a['letter']}"),
                    "correct": a["correct"]} for a in q["answers"]]
        questions.append({"type": "quiz", "question": question, "time": time_ms, "choices": choices,
                          "image_query": image})

    description = meta.get("description") or ", ".join(data["sections"])
    topic = meta["title"].replace(DEFAULTS["title_prefix"], "").split("(")[0]
    payload = {"title": meta["title"], "description": description[:LIMITS["description_max_chars"]],
               "language": "தமிழ்" if mode == "tamil_only" else "English",
               "cover_image_query": (meta.get("cover") or image_query(topic, "open bible"))[:100],
               "questions": questions}
    (folder / "kahoot-payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"payload": str(folder / "kahoot-payload.json"), "questions": len(questions), "notes": notes},
                     ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- record

def cmd_record(args):
    folder = quiz_dir(args.folder)
    meta = json.loads((folder / "quiz.json").read_text(encoding="utf-8"))["meta"]
    result = {"kahoot_id": args.kahoot_id, "url": args.url, "workspace": args.workspace,
              "created": dt.datetime.now().isoformat(timespec="seconds"), "title": meta.get("title")}
    (folder / "kahoot.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    index = folder.parent / "index.md"
    if not index.exists():
        index.write_text(f"# Igniters quizzes – {folder.parent.name}\n\n| Date | Quiz | Kahoot | Folder |\n|---|---|---|---|\n",
                         encoding="utf-8")
    link = f"[open]({args.url})" if args.url else args.kahoot_id or "—"
    with index.open("a", encoding="utf-8") as fh:
        fh.write(f"| {meta.get('date')} | {meta.get('title')} | {link} | [{folder.name}]({folder.name}/) |\n")
    pdf, _, engine = build_month_pdf(folder.parent.name)
    print(json.dumps({"saved": str(folder / "kahoot.json"), "index": str(index), "pdf": str(pdf) if pdf else None,
                      "engine": engine, "note": None if pdf else NO_PDF_HINT}, indent=2))


# ---------------------------------------------------------------- monthly PDF

CHROME_PATHS = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "google-chrome", "google-chrome-stable", "chromium", "chromium-browser")
SHEET_CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: "Helvetica Neue", Arial, "Noto Sans Tamil", "Tamil Sangam MN", sans-serif;
       font-size: 11.5pt; color: #111; }
.cover { text-align: center; margin-top: 35%; }
.cover h1 { font-size: 26pt; margin: 0 0 8px; }
.cover ol { text-align: left; display: inline-block; margin-top: 24px; font-size: 12pt; }
.quiz { page-break-before: always; }
.quiz h1 { font-size: 16pt; margin: 0; }
.quiz .date { color: #555; margin: 2px 0 14px; }
h2 { font-size: 12.5pt; margin: 16px 0 6px; }
.q { margin: 0 0 12px; page-break-inside: avoid; }
.q p { margin: 0; }
.q .ta { color: #333; }
.q ul { list-style: none; margin: 2px 0 0; padding: 0; }
.q li.correct { font-weight: 600; }
"""


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_quiz(data):
    """One quiz in the layout of the original Igniters sheets."""
    meta, out, section = data["meta"], [], None
    date = dt.date.fromisoformat(meta["date"])
    out.append(f'<section class="quiz"><h1>{esc(meta["title"])}</h1>'
               f'<p class="date">{date.strftime("%-d %B %Y")}</p>')
    for q in data["questions"]:
        if q["section"] and q["section"] != section:
            section = q["section"]
            out.append(f"<h2>{esc(section)}</h2>")
        heading = {"true_false": "True or False?", "multiple_select": "Multiple answer questions:"}.get(q["type"])
        lines = [f"{q['number']}. {esc(heading)}", esc(q["text"])] if heading else [f"{q['number']}. {esc(q['text'])}"]
        if q["tamil"]:
            lines.append(f'<span class="ta">{esc(q["tamil"])}</span>')
        answers = "".join(f'<li class="{"correct" if a["correct"] else ""}">{a["letter"]}) {esc(a["text"])}'
                          f'{" " + CHECK if a["correct"] else ""}</li>' for a in q["answers"])
        out.append(f'<div class="q"><p>{"<br>".join(lines)}</p><ul>{answers}</ul></div>')
    out.append("</section>")
    return "\n".join(out)


def build_month_pdf(month):
    month_dir = QUIZZES / month
    quizzes = []
    for folder in sorted(p for p in month_dir.iterdir() if p.is_dir()):
        path = folder / "quiz.json"
        if path.exists() and (data := json.loads(path.read_text(encoding="utf-8"))).get("valid"):
            quizzes.append(data)
    if not quizzes:
        sys.exit(f"No validated quizzes in {month_dir}")
    label = dt.date.fromisoformat(f"{month}-01").strftime("%B %Y")
    contents = "".join(f"<li>{esc(q['meta']['title'])}</li>" for q in quizzes)
    # Bundled Noto Sans Tamil so Tamil prints the same on the Mac and on Linux cloud machines
    fonts = Path(os.path.relpath(FONTS, month_dir)).as_posix()
    font_css = "".join(f'@font-face {{ font-family: "Noto Sans Tamil"; font-weight: {weight}; '
                       f'src: url("{fonts}/NotoSansTamil-{style}.ttf"); }}\n'
                       for weight, style in ((400, "Regular"), (700, "Bold")))
    html = (f'<!doctype html><html><head><meta charset="utf-8"><title>Igniters Youth Quiz – {label}</title>'
            f"<style>{font_css}{SHEET_CSS}</style></head><body>"
            f'<section class="cover"><h1>Igniters Youth Quiz</h1><p>{label}</p><ol>{contents}</ol></section>'
            + "".join(render_quiz(q) for q in quizzes) + "</body></html>")
    html_path = month_dir / f"igniters-quiz-{month}.html"
    pdf_path = month_dir / f"igniters-quiz-{month}.pdf"
    html_path.write_text(html, encoding="utf-8")
    engine = print_pdf(html_path, pdf_path)
    return (pdf_path if engine else None), len(quizzes), engine


def print_pdf(html_path, pdf_path):
    """Print the HTML with the first engine available: Chrome/Chromium, Playwright, WeasyPrint.

    IGNITERS_PDF_ENGINE=chrome|playwright|weasyprint forces one. Returns the engine used, or None.
    """
    forced = os.environ.get("IGNITERS_PDF_ENGINE")
    if forced in (None, "chrome"):
        for candidate in CHROME_PATHS:
            chrome = candidate if Path(candidate).exists() else shutil.which(candidate)
            if chrome:
                import subprocess
                subprocess.run([chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                                f"--print-to-pdf={pdf_path}", html_path.as_uri()],
                               check=True, capture_output=True, timeout=120)
                return "chrome"
    if forced in (None, "playwright"):
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(html_path.as_uri())
                page.pdf(path=str(pdf_path), prefer_css_page_size=True, print_background=True)
                browser.close()
            return "playwright"
        except Exception:  # not installed, or browser binaries missing
            pass
    if forced in (None, "weasyprint"):
        try:
            from weasyprint import HTML
            HTML(filename=str(html_path)).write_pdf(str(pdf_path))
            return "weasyprint"
        except Exception:
            pass
    return None


NO_PDF_HINT = ("No PDF engine found. Install one with: pip install playwright && "
               "python -m playwright install --with-deps chromium  (then run: quiz.py pdf YYYY-MM)")


def cmd_pdf(args):
    pdf, count, engine = build_month_pdf(args.month)
    print(json.dumps({"pdf": str(pdf) if pdf else None, "engine": engine, "quizzes": count,
                      "note": None if pdf else NO_PDF_HINT}, indent=2))
    sys.exit(0 if pdf else 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new")
    p.add_argument("--date", required=True, help="quiz date, YYYY-MM-DD")
    p.add_argument("--slug", required=True, help="short name, e.g. amos")
    p.add_argument("--source", help="PDF, DOCX or text file with the questions")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_new)
    for name, func in (("validate", cmd_validate), ("build", cmd_build)):
        p = sub.add_parser(name)
        p.add_argument("folder")
        if name == "build":
            p.add_argument("--language", choices=["combine_if_fits", "english_only", "tamil_only"])
            p.add_argument("--no-sections", dest="sections", action="store_false",
                           help="don't add a content slide before each section")
        p.set_defaults(func=func)
    p = sub.add_parser("record")
    p.add_argument("folder")
    p.add_argument("--kahoot-id")
    p.add_argument("--url")
    p.add_argument("--workspace")
    p.set_defaults(func=cmd_record)
    p = sub.add_parser("pdf", help="rebuild the month's PDF, e.g. pdf 2026-10")
    p.add_argument("month")
    p.set_defaults(func=cmd_pdf)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
