"""Read-only leaderboard presentation. Ranking comes from the core helpers."""

from __future__ import annotations

from decimal import Decimal
from html import escape
from pathlib import Path

import streamlit as st

from core.profile_photo import initials
from core.scoring_v1 import format_points
from photo_history_ui import identity_colour


def load_styles() -> None:
    css = (Path(__file__).parent / "assets" / "standings.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def reached_first(rows, index: int) -> bool:
    """True when the row below has the same points: this row ranks higher only
    because it reached the score first."""
    return index + 1 < len(rows) and Decimal(str(rows[index][1])) == Decimal(str(rows[index + 1][1]))


def _tie_tag(rows, index: int) -> str:
    return '<span class="standings-first-tag">reached first</span>' if reached_first(rows, index) else ""


def _podium_place(rank: int, member: str, points, names: dict, current_member: str, *, team_mode: bool,
                  extras: str = "") -> str:
    name = names.get(member, "Unknown player")
    you = member == current_member
    size = {1: ("48px", "124px", "16px"), 2: ("40px", "92px", "14px"), 3: ("40px", "68px", "14px")}[rank]
    avatar_size, block_height, name_size = size
    avatar_ring = "box-shadow:0 0 0 3px var(--brand-ink);" if rank == 1 else ""
    avatar_fill = "background:var(--accent);color:var(--on-accent);" if you else "background:var(--accent-soft);color:var(--text);"
    # Blocks: 1st our sky blue, 2nd silver, 3rd bronze; the numerals stay dark ink.
    block_fill = {1: "background:var(--accent);", 2: "background:var(--medal-2);", 3: "background:var(--medal-3);"}[rank]
    numeral_color = "var(--text)"
    tag = f'<span class="standings-podium-tag">{"YOUR TEAM" if team_mode else "YOU"}</span>' if you else ""
    return (
        f'<li class="standings-podium-place standings-podium-{rank}">'
        f'<span class="standings-podium-avatar" style="width:{avatar_size};height:{avatar_size};{avatar_fill}{avatar_ring}" aria-hidden="true">{escape(initials(name))}</span>'
        f'<span class="standings-podium-name" style="font-size:{name_size}">{escape(name)}{tag}{extras}</span>'
        f'<span class="standings-podium-points">{escape(format_points(points))}</span>'
        f'<span class="standings-podium-block" style="height:{block_height};{block_fill}">'
        f'<span style="color:{numeral_color}">{rank}</span></span></li>'
    )


def leaderboard(rows, names: dict, current_member: str, *, team_mode: bool = False) -> None:
    """Render rows in precisely the order returned by season_leaderboard: a
    podium for the top 3, then a flat ranked list for the rest."""
    podium = rows[:3]
    rest = rows[3:]

    if podium:
        ranked = dict(enumerate(podium, start=1))
        places = "".join(
            _podium_place(rank, *ranked[rank], names, current_member, team_mode=team_mode,
                          extras=_tie_tag(rows, rank - 1))
            for rank in (2, 1, 3) if rank in ranked
        )
        st.markdown(f'<ol class="standings-podium" aria-label="Top 3 this season">{places}</ol>', unsafe_allow_html=True)

    if rest:
        markup = '<ol class="standings-list" start="4">'
        for offset, (member, points) in enumerate(rest):
            rank = offset + 4
            name = names.get(member, "Unknown player")
            you = member == current_member
            row_class = " standings-row-you" if you else ""
            # Same hashed per-player colour as their photo-history frames,
            # so a face recurring across pages reads as the same identity.
            identity = {"team_id": member} if team_mode else {"membership_id": member}
            avatar_fill = f"background:{identity_colour(identity)};color:#fff;"
            tag = f'<span class="standings-you-tag">{"YOUR TEAM" if team_mode else "YOU"}</span>' if you else ""
            markup += (
                f'<li class="standings-row{row_class}"><span class="standings-row-rank">{rank}</span>'
                f'<span class="standings-row-avatar" style="{avatar_fill}" aria-hidden="true">{escape(initials(name))}</span>'
                f'<span class="standings-row-name">{escape(name)}{tag}{_tie_tag(rows, rank - 1)}</span>'
                f'<span class="standings-row-points">{escape(format_points(points))}</span></li>'
            )
        st.markdown(markup + "</ol>", unsafe_allow_html=True)


def territory_pills(territories, names: dict, current_member: str) -> None:
    markup = '<div class="standings-pills" role="list" aria-label="Territory ownership">'
    for territory, owner, _rows in territories:
        if owner == current_member:
            status, title = "territory-yours", "Yours"
        elif owner:
            status, title = "territory-theirs", f"Owned by {names.get(owner, 'another player')}"
        else:
            status, title = "territory-free", "Unclaimed"
        markup += (
            f'<div class="standings-pill {status}" role="listitem" title="{escape(title)}">'
            f'<span class="standings-pill-dot {status}"></span><span>{escape(territory.name)}</span></div>'
        )
    st.markdown(markup + "</div>", unsafe_allow_html=True)
