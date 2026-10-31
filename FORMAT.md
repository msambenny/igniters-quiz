# Igniters quiz format (standard output)

Questions can arrive in any format. Whatever comes in, it is rewritten into this layout as `formatted.md`. The layout matches the original Igniters quiz sheet, with a small header added on top. Reference copies: [examples/youth-quiz-4-oct-26.pdf](examples/youth-quiz-4-oct-26.pdf) is the sheet as received, and [examples/formatted-example.md](examples/formatted-example.md) is the same sheet fully formatted. The monthly PDF is printed from the same data, in the same layout.

```text
title: Igniters Youth Quiz – Amos (4 Oct 2026)
date: 2026-10-04
description: Book of Amos, chapters 1–9
time: 20

Chapters 1, 2

1. How many years 'before the earthquake' did Amos see visions concerning Israel? (Amos 1:1)
A) 1 year
B) 2 years ✅
C) 3 years
D) 4 years

Chapters 3, 4

6. Who did God choose/know from all the families of the earth? (Amos 3:2)
பூமியின் எல்லா வம்சங்களிலும் தேவன் யாரை அறிந்துகொண்டார்?
A) Egypt / எகிப்து
B) Israel / இஸ்ரவேல் ✅
C) Moab / மோவாப்
D) Judah / யூதா

Chapters 5, 6

11. True or False?
God Almighty would stir up a nation to oppress Israel. (Amos 6:14)
A) True ✅
B) False

14. Multiple answer questions:
What two virtues did the people turn into bitterness and poison? (Amos 5:7, 6:12)
A) Justice ✅
B) Righteousness ✅
C) Wisdom
D) Peace
```

## Rules

| Element | Rule |
|---|---|
| Header | Required: `title:` and `date:` (YYYY-MM-DD). The date decides the monthly folder. Optional: `description:`, `time:` (default seconds per question), and `cover:` (Unsplash search for the Kahoot cover image). |
| Section | A plain line such as `Chapters 3, 4`, exactly as on the sheet. `## Section name` also works for other kinds of section. |
| Question | `<n>. <text> (Book ch:v)`. Numbers run 1, 2, 3… with no gaps. The Bible reference stays here and in the PDF; it is removed only in Kahoot. |
| Tamil | Optional. The Tamil question goes on the line straight after the English one. Bilingual answers are written `English / Tamil`. |
| True/False | First line `<n>. True or False?`, then the statement on the next line, then `A) True` and `B) False` in either order. |
| Multiple answers | First line `<n>. Multiple answer questions:`, then the question, then two or more ✅ answers. |
| Answers | `A)` to `D)`, in order, one per line. |
| Correct mark | ` ✅` at the end of each correct answer. |
| Time | Optional `[time: 30]` right after the number. Allowed values: 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240. |
| Spacing | A blank line between questions. |

The parser also accepts `A.` for answers, a ✅ on its own line under an answer, and the tags `[tf]` and `[multi]`. When writing `formatted.md`, always use the layout above.

## Clean-up when formatting raw input

- `A.` / `a)` / `(a)` / `A -` → `A)`
- A correct answer marked with `*`, bold, `(correct)` or `Ans: B`, a ✅ on the next line, or a separate answer key at the end → ` ✅` at the end of that answer
- A reference without brackets, or at the front ("According to Amos 5:5, …") → `(Amos 5:5)` at the end of the question
- Smart quotes, ligatures (`ﬁ`, `ﬀ`) and stray spaces → plain text

## What Kahoot gets (made automatically by `build`)

- Bible references are removed from the question text (`strip_references` in `config.json`).
- All question, answer and section-slide text is wrapped in `<b>…</b>`, so it shows in bold (`bold` in `config.json`). Kahoot's True/False buttons use their own fixed labels.
- Every slide and question gets an `image_query` (Unsplash search) made from its key words, and the quiz gets a `cover_image_query` (from `cover:` if set). The Kahoot connector requires them.
- The length limits count the bold tags: 120 characters per question, 75 per answer.
