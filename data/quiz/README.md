# English Quiz Duel content

`general_en_v1.json` is the canonical, versioned bank: 100 English questions,
four distinct options per question, one zero-based correct index, an explanation,
topic, estimated difficulty, reference period, source and check date. It is
server-side application data, not a static browser download.

The contributor requested a lighter pool on 19 November 2026: **20 football and
80 general-knowledge questions**. Topics include geography, science, nature,
food, film/music, everyday technology, other sports/games and history/politics.
Older football statistics and detailed census questions were removed. Football
events and transfers refer to 2022 or later; a few timeless club facts remain.
Official club/competition sources support the recent football questions. Other
questions include reference links for team review. Current difficulty labels
are easy/easy-medium editorial estimates, not measured playtest results.

`core/quiz_questions.py` generates multiplication and logic questions at creation
time. They do not require stored lists of all possible examples. Five short logic
templates are used by default; the longer box puzzle is an explicit advanced
preview option. `data/quiz_questions.py`
loads the fixed bank and prepares a shared three-question pack.

The content is in the public course repository, so its answer key is not a secret.
Do not treat hiding the browser answer key as complete cheat prevention. A future
game server must still validate access, one-answer submissions, round timing and
the exact persisted option mapping.

The pack has a private JSON snapshot for a future Supabase JSONB field. Only its
active question's `public_payload` goes to a player. See
[`docs/QUIZ_QUESTION_PREPARATION.md`](../../docs/QUIZ_QUESTION_PREPARATION.md).
