# Igniters Youth Quiz → Kahoot

Pipeline (driven by the `igniters-quiz` Claude skill):

1. **Intake**: `python3 scripts/quiz.py new --date YYYY-MM-DD --slug <name> --source <file>` creates the monthly folder and extracts the raw text.
2. **Format**: Claude rewrites `raw.txt` into `formatted.md` using [FORMAT.md](FORMAT.md).
3. **Validate**: `python3 scripts/quiz.py validate <folder>` writes `quiz.json` and `validation.md`.
4. **Build + create**: `python3 scripts/quiz.py build <folder>` writes `kahoot-payload.json`, then Claude creates the quiz through the Kahoot! connector.
   Kahoot text is bold (`<b>` tags) and the Bible references are removed. The PDF keeps them.
5. **Record**: `python3 scripts/quiz.py record <folder> --kahoot-id … --url …` writes `kahoot.json`, updates `quizzes/YYYY-MM/index.md` and regenerates the monthly PDF.
6. **Monthly PDF**: run `python3 scripts/quiz.py pdf YYYY-MM` any time to rebuild `quizzes/YYYY-MM/igniters-quiz-YYYY-MM.pdf`.

Quizzes are stored in `quizzes/YYYY-MM/YYYY-MM-DD-<slug>/`. Limits and defaults are in [config.json](config.json).
The skill lives in `.claude/skills/igniters-quiz/` and is symlinked into `~/.claude/skills/` so it works from any folder.

## Using it from the phone (GitHub + Claude Code cloud sessions)

This folder is the private repo `github.com/msambenny/igniters-quiz`.

- **From the phone:** in the Claude app, open **Code**, start a new session on `msambenny/igniters-quiz` and send the questions. The session formats and validates the quiz, creates it in Kahoot!, saves the quiz and the month's PDF, pushes a branch and opens a pull request. Merge the PR (for example in the GitHub app) to keep the files.
- **On the Mac:** run `git pull` first. The skill does this for you.
- **PDF engine:** Chrome or Chromium is used if it's installed, otherwise Playwright (`pip install -r requirements.txt && python -m playwright install --with-deps chromium`), otherwise WeasyPrint. Tamil uses the bundled font in [fonts/](fonts/) (SIL Open Font License).
