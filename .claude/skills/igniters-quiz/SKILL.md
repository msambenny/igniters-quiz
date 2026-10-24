---
name: igniters-quiz
description: Turn Igniters youth Bible-quiz questions (PDF, Word, text or pasted, in English and/or Tamil, neat or messy) into a Kahoot through the Kahoot MCP connector. It formats the questions into the standard Igniters sheet layout, validates them, builds a bold, reference-free Kahoot, files everything in a monthly folder, and regenerates that month's PDF. Use whenever the user shares youth quiz questions, mentions Igniters, or asks to make or update a Kahoot quiz or the monthly quiz PDF for the youth.
---

# Igniters youth quiz → Kahoot

`$ROOT` is the `igniters-quiz` repository: the folder that contains `scripts/quiz.py` and this skill's `.claude/` folder. On the Mac it is `/Users/sambenny/code/igniters-quiz`. In a Claude Code cloud session (for example one started from the phone) it is the checked-out repo, usually the current directory. The repo is `github.com/msambenny/igniters-quiz` (private). Run every command from `$ROOT`:

```bash
python3 scripts/quiz.py <new|validate|build|record> ...
```

- `$ROOT/FORMAT.md` describes the standard format. Read it before Stage 2. `$ROOT/examples/` holds the original example sheet and a fully formatted version of it, for reference only. Never record or publish the examples.
- `$ROOT/config.json` holds the Kahoot limits, the default time per question and the language mode.

Run the stages in order. Don't skip validation, and don't send anything to Kahoot before the user approves it.

## Stage 0: Sync

Quizzes are made both on the Mac and from the phone in cloud sessions, and the GitHub repo is what keeps them in step.

- **On the Mac:** run `git pull --ff-only` before you start, so you have any quizzes made from the phone.
- **In a cloud session:** you start from a fresh checkout, so there's nothing to pull.
  - Make sure a PDF engine is available. Check with `python3 -c "import playwright"` or `which chromium`.
  - If neither is there, run `pip install playwright && python -m playwright install --with-deps chromium` in the background while you work on Stages 1–3.
  - If that install fails, carry on: the quiz still gets made, and the PDF can be rebuilt later on the Mac with `quiz.py pdf YYYY-MM`.

## Stage 1: Intake

1. Find the quiz date. Use the date in the file name or heading (e.g. `youth-quiz-4-oct-26` → `2026-10-04`). If there isn't one, ask. Pick a short slug, usually the Bible book or theme (`amos`).
2. Create the folder and extract the text:
   ```bash
   python3 scripts/quiz.py new --date 2026-10-04 --slug amos --source "/path/to/file.pdf"
   ```
   This creates `quizzes/YYYY-MM/YYYY-MM-DD-slug/` with `source/` (the original file) and `raw.txt`.
   If the user pasted the questions, leave out `--source` and save the text to `raw.txt` yourself.
3. Read the `notes` in the output. **Tamil from PDFs often comes out garbled** (glyph names like `/ka_uசatraஇtamil`). When that happens:
   - Try reading the PDF pages visually.
   - If that fails, ask the user for a .docx or text copy.
   - If neither works, go ahead in English only and tell the user which Tamil lines were dropped.
   - Never guess or make up Tamil text.

## Stage 2: Format

The input can arrive in any format. The output must always follow the Igniters example sheet layout in `FORMAT.md`. Rewrite `raw.txt` into `formatted.md` in the same folder:

- Write the header: `title`, `date`, and optionally `description` and `time`. The default title is `Igniters Youth Quiz – <Book/Theme> (<D Mon YYYY>)`.
- Write section lines in plain text, e.g. `Chapters 1, 2`.
- Keep the question order and the Bible references `(Amos 3:7)`. They stay in this file and in the PDF; `build` removes them for Kahoot only.
- Put a ` ✅` at the end of each correct answer's line. Correct answers may be marked in the input with ✅ on its own line, `*`, bold, `Ans: B` or an answer key.
- True/False questions start with the line `<n>. True or False?`, with the statement on the next line.
- Questions with several correct answers start with the line `<n>. Multiple answer questions:`, with the question on the next line.
- If a question has Tamil, put it on the line after the English question. Bilingual answers are written `English / Tamil`.
- Fix spelling and grammar in the English only where the meaning is clearly unchanged, e.g. "pregnant woman" → "pregnant women" (Amos 1:13). **Never change which answer is correct, and never invent answers.** If a question has no correct mark, or the mark is ambiguous, leave it unmarked. Validation will flag it, and you then ask the user.
- In Kahoot each question can be at most 120 characters, and each answer at most 75. Those counts exclude the reference but include the 7-character `<b></b>` bold tags. If validation says a question is too long, shorten its wording but keep the meaning. Note every question you shorten for the report.

## Stage 3: Validate

```bash
python3 scripts/quiz.py validate quizzes/YYYY-MM/YYYY-MM-DD-slug
```

This writes `quiz.json` and `validation.md`, which contains the errors, the warnings and an answer key.

- **Errors**: fix the ones that are formatting problems in `formatted.md` and validate again. Repeat until it passes. If an error needs a content decision (a missing correct answer, unclear options, a wrong count), ask the user. Don't guess.
- **Warnings**: fix them if the fix is obvious, otherwise mention them to the user.
- When it passes, check the content yourself as well. Where the user hasn't already confirmed an answer and it looks wrong for the cited verse, list it as a question. Don't change it.

Show the user a short summary before going further:

- the number of questions by type
- any changes you made
- warnings and dropped Tamil
- the answer key from `validation.md`

Ask the user to approve it.

## Stage 4: Build and create in Kahoot

1. Build the payload:
   ```bash
   python3 scripts/quiz.py build quizzes/YYYY-MM/YYYY-MM-DD-slug [--language english_only]
   ```
   This writes `kahoot-payload.json`.
   The payload is already in the connector's input shape, so pass `title`, `description`, `language` and `questions` straight through. Add `--no-sections` if the user doesn't want the "Chapters …" content slides.
   - Bible references are removed from the questions, and all question, answer and slide text is wrapped in `<b>…</b>`, so it's bold. Both are switched on in `config.json` (`strip_references`, `bold`). Don't take the tags out.
   - Normal question: `{type:"quiz", question, time, choices:[{answer, correct}]}`. `time` is in milliseconds.
   - True/False question: `{type:"true_false", question, correct:true|false, time}`.
   - Section heading: `{type:"content", title}`.
   - Kahoot has no "select all" type. A `[multi]` question becomes a quiz question with several correct answers, and a player scores by picking any one of them. Tell the user this happens.
2. Check that the Kahoot connector is available. Its tools are `create_or_update_kahoot`, `get_workspaces`, `get_kahoot`, `get_kahoot_editor_url` and `preview_kahoot`, with a server prefix like `mcp__<uuid>__`. If they're missing, load them with ToolSearch (`kahoot`).

   If the tools still aren't there:
   - Tell the user to connect **Kahoot!** under Settings → Connectors. In a cloud session, they may also need to enable it for the session.
   - Do Stage 5 anyway, so the validated quiz and payload are saved.
   - Stop there. Tell the user they can finish from the Mac, where you create the Kahoot from `kahoot-payload.json` and then run `record`.
3. Call `create_or_update_kahoot`:
   - Optionally add a `cover_image_query`, e.g. `ancient scroll bible reading`.
   - **Leave out `folderId`.** The user's account refuses its workspace ids ("You don't have access to the folder"). Without a folder, the quiz is saved to the user's default library, the msambenny workspace. Pass a `folderId` only if the user asks for a specific folder.
   - To update an existing quiz, pass `uuid` from `kahoot.json` along with the **full** payload. Updates replace the whole quiz.
   - Don't create a duplicate.
   - Don't call `preview_kahoot` as well; create already shows a preview.
   - Kahoot shuffles the answer order itself. That's expected and the correct flags are kept.
4. Get the editor link (`get_kahoot_editor_url`), then record it:
   ```bash
   python3 scripts/quiz.py record quizzes/YYYY-MM/YYYY-MM-DD-slug --kahoot-id <id> --url <editor-or-play-url> [--workspace <name>]
   ```
   This writes `kahoot.json`, adds a row to `quizzes/YYYY-MM/index.md`, and **regenerates the monthly PDF** `quizzes/YYYY-MM/igniters-quiz-YYYY-MM.pdf`. The PDF has a cover page, then every validated quiz of that month in the sheet layout, with ✅ on the correct answers.
   - The first engine found prints the PDF: Chrome or Chromium, then Playwright, then WeasyPrint. The Noto Sans Tamil font in `fonts/` is included, so Tamil prints correctly on any machine.
   - If the output shows `"pdf": null`, no engine was found. Install one (see Stage 0) and run `quiz.py pdf YYYY-MM` again.
   - After editing a quiz without re-recording it, rebuild the PDF with `python3 scripts/quiz.py pdf YYYY-MM`.

## Stage 5: Save to GitHub

Commit the new quiz folder, the month's `index.md`, the PDF and the HTML, using a commit message like `Add 2026-11-02 Ruth quiz`. Then push.

- **On the Mac:** commit to `main` and run `git push`.
- **In a cloud session:**
  - Push the session's branch. Cloud sessions usually aren't allowed to push to `main`.
  - Then open a pull request with the app's **Create PR** button, or with `gh pr create` if that's available. Tell the user to merge it; the GitHub app on the phone works for that.
  - Until the PR is merged, the Mac and later sessions won't see this quiz, and the next month's PDF will be missing it.
- If a push fails, say so and leave the commit in place. Never force-push.

## Stage 6: Report

Give the user:

- the Kahoot link
- the number of questions
- the folder path and the path of the month's PDF
- anything that still needs a person, such as warnings, dropped Tamil, or questions you shortened

## Monthly folder layout

```
quizzes/
  2026-10/
    index.md                      ← every quiz of the month with its Kahoot link
    igniters-quiz-2026-10.pdf     ← monthly printable sheet (all quizzes, answers ✅)
    igniters-quiz-2026-10.html    ← source of the PDF
    2026-10-04-amos/
      source/youth-quiz-4-oct-26.pdf
      raw.txt                     ← extracted text (Stage 1)
      formatted.md                ← standard format (Stage 2, hand-editable)
      quiz.json  validation.md    ← Stage 3
      kahoot-payload.json         ← Stage 4
      kahoot.json                 ← created Kahoot id + link
```

To change a quiz later:

1. Edit `formatted.md`.
2. Run `validate` and `build` again.
3. Update the Kahoot using the `kahoot_id` in `kahoot.json`.
