"""Photo-card presentation using authorized image bytes and stored entry values."""
from __future__ import annotations

from base64 import b64encode
from datetime import datetime, time, timedelta
from decimal import Decimal
from html import escape
from hashlib import sha256
from zoneinfo import ZoneInfo

import streamlit as st

from core.scoring_v1 import DRINK_LABELS, format_points, size_label, utc, window_bounds


def _entry_time(entry: dict) -> datetime:
    timestamp = entry.get("captured_at") or entry["submitted_at"]
    return utc(datetime.fromisoformat(timestamp))


def game_night_bounds(entry: dict) -> tuple[datetime, datetime]:
    """The Thu 18:00-Sun 18:00 game night containing this entry's timestamp.
    Uses the season's own rules (so a QA season's shifted window groups
    correctly) and falls back to the standard window for legacy entries
    with no season object."""
    ts = _entry_time(entry)
    season = entry.get("season")
    if season is not None:
        return window_bounds(ts, season)
    zone = ZoneInfo(entry.get("timezone_name", "UTC"))
    local = ts.astimezone(zone)
    monday = local.date() - timedelta(days=local.weekday())
    start = datetime.combine(monday + timedelta(days=3), time(18), zone)
    end = datetime.combine(monday + timedelta(days=6), time(18), zone)
    return start, end


def game_night_label(start: datetime, end: datetime) -> str:
    last_day = end - timedelta(days=1)  # end is exclusive Sunday 18:00
    if start.month == last_day.month:
        return f"Game night · {start:%d}–{last_day:%d %b}"
    return f"Game night · {start:%d %b}–{last_day:%d %b}"


def memory_tile(entry: dict, photo: bytes | None, *, key: str) -> bool:
    """One tap-to-open grid tile: photo, points badge and a territory dot,
    overlaid with a transparent full-tile button. Returns True once clicked."""
    name = entry["username"]
    if entry.get("team_id"):
        name = f"{entry.get('team_name') or 'Team'} · {name}"
    model = entry.get("entry")
    kind = model.drink_type if model else entry.get("drink_type")
    label = DRINK_LABELS.get(kind, "Long drink" if kind == "longdrink" else kind or "Drink")
    if model and model.size:
        label += f" · {size_label(kind, model.size, entry['season'].scoring_rules)}"
    points = model.points_awarded + model.time_bonus if model else entry.get("base_points")
    matched = entry["location"] == "matched"
    colour = identity_colour(entry)
    if photo is not None:
        encoded = b64encode(photo).decode("ascii")
        photo_html = f'<img class="memory-photo" src="data:image/jpeg;base64,{encoded}" alt="">'
    else:
        photo_html = '<div class="memory-photo memory-photo-missing"></div>'
    badge = f'<span class="memory-points">+{escape(format_points(points))}</span>' if points is not None else ""
    dot = f'<span class="memory-dot {"memory-dot-matched" if matched else "memory-dot-outside"}" aria-hidden="true"></span>'
    st.html(
        f'<div class="memory-tile-visual" style="--photo-identity:{colour}">{photo_html}{badge}{dot}</div>'
        f'<div class="memory-meta"><strong>{escape(name)}</strong><span>{escape(label)}</span></div>'
    )
    return st.button(f"View {name}'s check-in", key=f"{key}_open")


def identity_colour(entry: dict) -> str:
    """A stable identity colour across pagination, renames and app restarts."""
    identity = (f"team:{entry['team_id']}" if entry.get("team_id") else
                f"player:{entry.get('player_id') or entry.get('membership_id') or entry['username']}")
    hue = int.from_bytes(sha256(identity.encode()).digest()[:4], "big") / 2**32 * 360
    return f"hsl({hue:.3f} 60% 42%)"


def framed_photo(entry: dict, photo: bytes | None, *, detail: bool = False) -> None:
    name = entry["username"]
    if entry.get("team_id"):
        name = f"{entry.get('team_name') or 'Team'} · {name}"
    # Identity-derived colour only; all names are escaped and images stay inline.
    colour = identity_colour(entry)
    label = f'<figcaption class="history-photo-identity">{escape(name)}</figcaption>'
    if photo is not None:
        encoded = b64encode(photo).decode("ascii")
        image = (f'<img class="{"drink-photo" if detail else "history-photo"}" '
                 f'src="data:image/jpeg;base64,{encoded}" alt="Check-in photo by {escape(name, quote=True)}">')
        st.html(f'<figure class="history-photo-frame" style="--photo-identity:{colour}">{label}{image}</figure>')
    else:
        st.markdown(f'<figure class="history-photo-frame" style="--photo-identity:{colour}">{label}'
                    '<div class="history-photo-missing">Photo unavailable</div></figure>', unsafe_allow_html=True)


def photo_metadata(entry: dict) -> None:
    """Show stored selections/awards, including historical legacy entries."""
    model = entry.get("entry")
    kind = model.drink_type if model else entry.get("drink_type")
    selection = DRINK_LABELS.get(kind, "Long drink" if kind == "longdrink" else kind or "Drink details unavailable")
    if model and model.size:
        selection += f" · {size_label(kind, model.size, entry['season'].scoring_rules)}"
    points = model.points_awarded if model else entry.get("base_points")
    if points is None:
        award = "Points unavailable"
    else:
        territory_points = points if entry["location"] == "matched" else 0
        season_points = entry.get("duel_season_points", points) if entry.get("duel_id") else points + (model.time_bonus if model else 0)
        award = f"+{format_points(season_points)} season pts · +{format_points(territory_points)} territory pts"
    timestamp = entry.get("captured_at") or entry["submitted_at"]
    zone = ZoneInfo(entry.get("timezone_name", "UTC"))
    time = utc(datetime.fromisoformat(timestamp)).astimezone(zone)
    time_label = "Photo received" if entry.get("captured_at") else "Submitted"
    st.markdown(f'<div class="history-card-details"><h3>{escape(selection)}</h3>'
                f'<p class="history-award">{escape(award)}</p>'
                f'<p class="history-time">{time_label} · {time:%d %b %Y · %H:%M %Z}</p></div>',
                unsafe_allow_html=True)
    if entry.get("duel_id"):
        st.caption("Chug Duel · Shared capture · Drink selection agreed by both players.")
    if model and model.time_bonus:
        st.caption('Time Duel ×1.25 · Included in season points only.')
    if model and model.focus_attempt_id:
        st.caption('Focus boost ×1.5 · Included in the displayed season and territory awards.')
    bonus = model.owner_bonus_quarters if model else entry.get("owner_bonus_quarters", 0)
    if bonus:
        income = format_points(Decimal(bonus) / 4)
        st.markdown(f'<p class="history-owner-income">Owner income: +{income} pts to '
                    f'{escape(entry.get("income_recipient") or "Lobby member")}</p>', unsafe_allow_html=True)
