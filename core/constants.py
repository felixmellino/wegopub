"""Every tunable game-rule number, in one place. Change behavior here,
nowhere else. Values marked 'placeholder' are the team's defaults from the
2026-11-17 sync, not final -- see docs/ontology/OPEN_DECISIONS.md."""

from datetime import time

# -- scoring (placeholder values, D-02 in OPEN_DECISIONS.md) --------------

BEER_POINTS_PER_UNIT = 5
WINE_POINTS_PER_UNIT = 5
SHOT_POINTS = 10
LONGDRINK_POINTS = 15

ALLOWED_DRINK_TYPES = {"beer", "wine", "shot", "longdrink"}
# Drink types whose points scale with an amount (size); others are flat.
AMOUNT_SCALED_DRINK_TYPES = {"beer", "wine"}

# -- game window (placeholder exact hours, D-05 in OPEN_DECISIONS.md) -----
# One continuous block per week: Thursday 12:00 through Sunday 23:59:59.
# Monday = 0 ... Sunday = 6.

WINDOW_START_WEEKDAY = 3  # Thursday
WINDOW_START_TIME = time(12, 0, 0)
WINDOW_END_WEEKDAY = 6  # Sunday
WINDOW_END_TIME = time(23, 59, 59)

# -- duplicate check-in guard (D-12 in OPEN_DECISIONS.md) ------------------

DUPLICATE_WINDOW_SECONDS = 120

# -- location (R-L02 in RULES.md) ---------------------------------------
# A phone reading may be off by at most this many metres; worse is uncertain.

MAX_GPS_ACCURACY_M = 50.0

# A phone reading older than this many seconds is not used (R-L04).
MAX_GPS_AGE_SECONDS = 60

# -- photo privacy (R7 in RULES.md) -------------------------------------

PHOTO_RETENTION_DAYS = 30
# Allow a failed database save to be retried before removing its upload.
UNLINKED_PHOTO_GRACE_HOURS = 24

# -- season length (D-06 in OPEN_DECISIONS.md) ------------------------------
# Calendar months are ambiguous; these day counts are a placeholder.

SEASON_LENGTH_DAYS = {
    "1_week": 7,
    "1_month": 30,
    "3_months": 91,
}

# -- minigames ---------------------------------------------------------

MAX_MINIGAME_PLAYS_PER_WINDOW = 1
