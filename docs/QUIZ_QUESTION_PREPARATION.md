# Quiz Duel: content preparation

19 November 2026. This document describes the original content foundation.
Playable invitations, reserved stakes and timed rounds are now implemented on
the feature branch; see [the current handoff](QUIZ_DUEL.md). The sections below
preserve how the content was prepared before gameplay was added.

## How the content works

1. **General knowledge:** choose one of 100 easy/easy-medium English questions from
   `data/quiz/general_en_v1.json`. Each includes four choices, a correct index,
   explanation and source. The file is the source of truth; no manual Supabase
   import or external question API is needed. The revised pool contains 20
   football and 80 broader general-knowledge questions. Football events and
   transfers are from 2022 onward. Older niche statistics/census questions are
   removed; difficulty labels still need casual team playtesting.
2. **Multiplication:** randomly choose two whole numbers from 1 through 10.
   Compute their product. Wrong choices come from neighbouring multiplication
   results, nearby numbers or the common mistake of adding the two factors.
   Remove collisions, zero and numbers above 100; then select three wrong
   answers and shuffle all four. This handles both 1×1 and 10×10.
3. **Logic:** generate one of six tested templates: alternating explicit
   operations, finishing order, universal deduction, exclusion, conditional
   deduction, or a four-box puzzle with exactly one true statement. Random
   names, colours and numbers create variants. The first five short templates
   form the easy default; the longer box puzzle is only available when explicitly
   selected in the developer preview. Rules are explicit; an
   ambiguous visual pattern or a subjectively odd word is not used.

Both players get the same question and choice order. Generate once through
`prepare_pack`, persist its private `snapshot`, then load that exact snapshot
for both players and after reconnects. Never call the generator independently
on each phone. The SHA-256 fingerprint detects a changed snapshot; it is not a
signature or authorization mechanism.

The normal pack is ordered general knowledge, multiplication, logic. The agreed
best-of-three game can skip the third question after a 2:0. `prepare_decider`
can provide a fresh general-knowledge question, excluding already-used IDs.
This helper does not implement winner detection or decide how many tie-break
attempts are permitted.

## Supabase preparation

The bank belongs in version control. Re-uploading all 100 questions would add a
second copy to maintain. For the eventual game, store a private snapshot in the
duel record's JSONB field alongside the participants and current round. The
snapshot is plain JSON and versioned independently from the question bank.

The later migration must restrict the answer-bearing column/table to the
server service role. The player response must contain only the authorized active
`public_round`: pack ID, round number, question ID, category, text and four options.
Do not return future questions, correct indexes, explanations, the server seed,
or the private snapshot before they are eligible to be revealed.

No new SQL is needed for this content-only preparation. The assistant will handle
the actual duel storage/migration and deployment in the implementation step;
the contributor does not need to import the earlier CSV or JSON manually.
The future point transfer must be atomic and exactly once, separate from drink
entries, territory points and owner income.

## Verify and preview

From the quiz worktree with the project's virtual environment active:

```powershell
python scripts/prepare_quiz_questions.py
python -m pytest tests/test_quiz_questions.py tests/test_quiz_question_preview.py -q
python -m streamlit run scripts/preview_quiz_questions.py
```

Optional private fixture export (gitignored; never expose it as a player asset):

```powershell
python scripts/prepare_quiz_questions.py --snapshot .venv/quiz-pack-preview.json
```

Tests cover all 100 factor pairs, invalid factors and indexes, unique alternatives,
shuffling, each logic template, exhaustive truth checks for box puzzles, a shared
pack's JSON reload, missing/duplicate bank entries and no answer fields in public
payloads. AppTest and the developer preview exercise all three categories, the
10×10 boundary and retaining one pack across round changes. No production database
is touched. Refresh/restart recovery of a real duel remains part of the later
Supabase implementation, rather than a claim of this content-only patch.

Verification on 19 November 2026: all 782 pytest tests passed after integration
with current main, including the 141 question/preview tests. The existing 315
Streamlit/NumPy timedelta deprecation warnings remain.
The content checker/export command passed. The optional Playwright browser check
passed at 390 px and 1280 px, including one saved pack across rounds, 10×10,
the longer box puzzle and answer/source review. Preview screenshots are local,
gitignored artifacts.

To repeat the optional browser check, start the preview with `--server.port 8769`
and run `node tests/quiz_question_browser.cjs <path-to-installed-playwright>`.
It uses local Chromium or Edge and requires no production frontend dependency.
