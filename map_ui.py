"""Map page presentation: territories coloured by owner, your position.

Ownership and the capture gap come from core/territories.py; this file only
turns them into map shapes, colours and text. No game rules live here.
"""

from __future__ import annotations

import math
import re
from html import escape
from pathlib import Path

import pydeck as pdk
import streamlit as st

from core.territories import capture_status, territory_owner, territory_standings
from core.scoring_v1 import replay_season, format_points
from map_markers import owner_markers

# Colour = what the territory means for you (RGB). Same values as the
# --territory-* tokens in assets/theme.css (design system "Tennis").
COLOURS = {
    "yours": [44, 153, 214],    # #2C99D6 Sky Blue
    "theirs": [235, 47, 51],    # #EB2F33 Scarlet Red
    "free": [138, 151, 166],    # #8A97A6 grey
}
FILL_ALPHA = {"yours": 150, "theirs": 150, "free": 55}
# Every border is plain white, so each area stands out clearly on the dark
# map; the fill colour alone says who owns it.
LINE_COLOUR = [255, 255, 255, 255]
LEGEND = {"yours": "Yours", "theirs": "Someone else's", "free": "Unclaimed"}
HOVER_COLOUR = [255, 255, 255, 70]  # lightens the area under the pointer

# Quick-zoom buttons: which territory ids belong to which part of the city.
# Ids that aren't in the territory file are simply skipped.
_BAIRRO_ALTO = ["rua-dos-mouros", "cheers-irish-pub", "le-pub", "shortys",
                "party-street", "outer-bairro", "rua-da-rosa", "autschan"]
AREAS = {
    "Bairro Alto": _BAIRRO_ALTO,
    "Lisbon": _BAIRRO_ALTO + [
        "santa-catarina", "tower-bar", "santos-kiosk", "after8", "principe-real",
        "praca-das-flores", "sao-bento", "madragoa", "calcada-do-combro", "bica",
        "sao-paulo", "time-out-market", "pink-street", "chiado", "sao-pedro-de-alcantara"],
    "Nova SBE": ["nova-sbe", "carcavelos-centro", "rebelva"],
    "Jamor Golf": ["jamor-golf"],
}
ME = ":material/my_location: Me"
ALL = "All"


def load_styles() -> None:
    """Game-style page: dark background, floating HUD and card (assets/game_map.css)."""
    css = (Path(__file__).parent / "assets" / "game_map.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def hud(lobby_name: str, rows: list[dict]) -> None:
    """Slim bar floating over the map: the lobby, and how many territories
    are yours, a rival's and free. The coloured numbers double as the legend."""
    numbers = summary(rows)
    rivals = numbers["total"] - numbers["yours"] - numbers["free"]
    st.markdown(
        f'<div class="game-hud"><strong class="game-hud-lobby">{escape(lobby_name)}</strong>'
        f'<span class="game-hud-counts"><b class="game-yours">{numbers["yours"]}</b> yours'
        f'<b class="game-theirs">{rivals}</b> rivals'
        f'<b class="game-free">{numbers["free"]}</b> free</span></div>',
        unsafe_allow_html=True,
    )


def location_card(here: dict | None, status: str, accuracy_m: float | None = None) -> None:
    """Bottom card floating over the map: where you are and what it means.
    status: "matched", "outside", "inaccurate", "denied" or "waiting"."""
    if status == "matched" and here:
        tone = {"yours": "game-yours", "theirs": "game-theirs"}.get(here["status"], "")
        body = (f'<small>You are in</small><h3>{escape(here["name"])}</h3>'
                f'<p class="{tone}">{escape(here["detail"])}</p>')
    elif status == "outside":
        body = "<small>You are</small><h3>Outside the map</h3><p>Drinks here count for season points only.</p>"
    elif status == "inaccurate":
        body = (f"<small>Location</small><h3>Not precise enough</h3>"
                f"<p>Accurate to about {accuracy_m:.0f} m, we need 50 m. Step outside for a moment.</p>")
    elif status == "denied":
        body = "<small>Location</small><h3>Location is blocked</h3><p>Allow location for this site in your browser settings.</p>"
    else:
        body = "<small>Location</small><h3>Finding you…</h3><p>Allow location access if your browser asks.</p>"
    st.markdown(f'<div class="game-card">{body}</div>', unsafe_allow_html=True)


def markdown_safe(text: str) -> str:
    """Usernames are free text: stop them from being read as Markdown."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~$])", r"\\\1", text)


def territory_rows(territories, entries, me: str, names: dict) -> list[dict]:
    """One row per territory with everything the map and list show."""
    rows = []
    snapshot = replay_season(entries) if any(e.rule_version == "v1" for e in entries) else None
    point_step = .5 if any(e.focus_attempt_id for e in entries) else 1
    for territory in territories:
        owner = snapshot.owners.get(territory.id) if snapshot else territory_owner(entries, territory.id)
        standings = snapshot.territory_rows(territory.id) if snapshot else territory_standings(entries, territory.id)
        status, number = capture_status(standings, owner, me, point_step=point_step)
        needed = number if status == "theirs" else None
        my_points = dict(standings).get(me, 0)
        owner_name = names.get(owner, "Unknown player") if owner else "Nobody"
        # The standings are already in ranking order (ties: who reached the score first).
        ranking = [{"id": who, "name": names.get(who, "Unknown player"), "points": points, "you": who == me}
                   for who, points in standings]
        if status == "free":
            detail = "Unclaimed: your next drink here claims it."
        elif status == "yours":
            detail = f"Yours: you lead by {format_points(number)} point{'s' if number != 1 else ''}."
        else:
            detail = f"Owned by {owner_name}: you need {format_points(number)} more point{'s' if number != 1 else ''} to take it."
        rows.append({
            "id": territory.id,
            "name": territory.name,
            "status": status,
            "owner": owner_name,
            "owner_id": owner,
            "owner_points": dict(standings).get(owner, 0),
            "my_points": my_points,
            "needed": needed,
            "ranking": ranking,
            "detail": detail,
            "boundary": territory.boundary,
        })
    return rows


def summary(rows: list[dict]) -> dict:
    """Numbers for the cards above the map. 'easiest' is the territory someone
    else owns that needs the fewest points to take (None if there's none)."""
    yours = sum(1 for row in rows if row["status"] == "yours")
    free = sum(1 for row in rows if row["status"] == "free")
    theirs = [row for row in rows if row["status"] == "theirs"]
    easiest = None
    if theirs:
        best = min(theirs, key=lambda row: (row["needed"], row["name"]))
        easiest = (best["name"], best["needed"])
    return {"yours": yours, "total": len(rows), "free": free, "easiest": easiest}


def view_for(rows: list[dict], focus: str, location: tuple[float, float] | None) -> pdk.ViewState:
    """Where the map starts: on you, or zoomed to fit one part of the city."""
    if focus == ME and location is not None:
        return pdk.ViewState(latitude=location[0], longitude=location[1], zoom=15.5)
    ids = set(AREAS.get(focus, []))
    points = [p for row in rows if row["id"] in ids for p in row["boundary"]["coordinates"][0]]
    if not points:  # "All" (or an unknown area): fit every territory
        points = [p for row in rows for p in row["boundary"]["coordinates"][0]]
    lngs, lats = [p[0] for p in points], [p[1] for p in points]
    # Zoom so the area's width and height fit the map (~420 x 480 px; a bit
    # of it may run off a narrow phone screen, which is fine).
    # The map library draws the whole world 512 px wide at zoom 0.
    span_lng = max(max(lngs) - min(lngs), 1e-4)
    span_lat = max(max(lats) - min(lats), 1e-4) / math.cos(math.radians(sum(lats) / len(lats)))
    zoom = min(math.log2(420 * 360 / (512 * span_lng)), math.log2(480 * 360 / (512 * span_lat))) - 0.2
    return pdk.ViewState(latitude=(min(lats) + max(lats)) / 2, longitude=(min(lngs) + max(lngs)) / 2,
                         zoom=max(9.0, min(zoom, 17.0)))


TOP_N = 5  # the tooltip stays tiny: only the best few players
TOOLTIP_STYLE = {"backgroundColor": "rgba(255,255,255,.96)", "color": "#142B3D", "padding": "6px 10px",
                 "borderRadius": "10px", "fontSize": "12px", "lineHeight": "1.35", "minWidth": "110px",
                 "maxWidth": "170px", "boxShadow": "0 4px 14px rgba(20,43,61,.25)"}


def tooltip_rows(row: dict) -> dict:
    """The tooltip's little list as plain text properties (name1/points1 ...).
    No HTML: the map's tooltip escapes every value, so usernames are safe."""
    props = {}
    shown = row["ranking"][:TOP_N]
    for place in range(TOP_N):
        entry = shown[place] if place < len(shown) else None
        props[f"n{place + 1}"] = (entry["name"] + (" (you)" if entry["you"] else "")) if entry else ""
        props[f"p{place + 1}"] = format_points(entry["points"]) if entry else ""
    props["more"] = "…" if len(row["ranking"]) > TOP_N else ""
    props["none"] = "" if row["ranking"] else "no points yet"
    return props


TOOLTIP_HTML = ('<div class="tt-name">{name}</div>'
                + "".join(f'<div class="tt-row"><span>{{n{i}}}</span><b>{{p{i}}}</b></div>' for i in range(1, TOP_N + 1))
                + '<div class="tt-none">{more}{none}</div>')


def render_map(rows: list[dict], location: tuple[float, float] | None, accuracy_m: float | None,
               focus: str = "Bairro Alto", *, pictures=None, context="map") -> None:
    features = [
        {
            "type": "Feature",
            "geometry": row["boundary"],
            "properties": {
                # Plain text only: the tooltip escapes values, so usernames can't inject HTML.
                "name": row["name"],
                **tooltip_rows(row),
                "fill": COLOURS[row["status"]] + [FILL_ALPHA[row["status"]]],
            },
        }
        for row in rows
    ]
    layers = [
        pdk.Layer(
            "GeoJsonLayer",
            {"type": "FeatureCollection", "features": features},
            id="territories",
            pickable=True,
            auto_highlight=True,
            highlight_color=HOVER_COLOUR,
            stroked=True,
            filled=True,
            get_fill_color="properties.fill",
            get_line_color=LINE_COLOUR,
            line_width_min_pixels=2.5,
        )
    ]
    markers = owner_markers(rows, pictures or {}, COLOURS)
    # Marker tooltip strings are HTML too; the unescaped owner name stays server-side.
    for marker in markers:
        marker["name"] = escape(marker["name"])
    layers += [
        pdk.Layer("IconLayer", markers, id="owner-badges", get_position="position", get_icon="icon",
                  get_size="size", size_units="meters", size_min_pixels=12, size_max_pixels=52,
                  pickable=False, billboard=True),
        pdk.Layer("TextLayer", markers, id="owner-initials", get_position="position", get_text="initials",
                  get_size="text_size", size_units="meters", size_min_pixels=6, size_max_pixels=16,
                  get_color=[255, 255, 255, 255], font_weight=800, billboard=True,
                  get_text_anchor="'middle'", get_alignment_baseline="'center'", pickable=False),
    ]
    # No territory names on the map (too crowded with 48 areas): the name shows on hover.
    if location is not None:
        here = [{"lng": location[1], "lat": location[0], "radius": accuracy_m or 0}]
        layers += [
            pdk.Layer("ScatterplotLayer", here, id="gps-accuracy", get_position="[lng, lat]", get_radius="radius",
                      get_fill_color=[255, 255, 255, 40], stroked=False),
            pdk.Layer("ScatterplotLayer", here, id="gps-position", get_position="[lng, lat]", get_radius=1,
                      radius_min_pixels=8, get_fill_color=[255, 255, 255, 255],  # --you-dot
                      get_line_color=[20, 43, 61, 255], stroked=True, line_width_min_pixels=3),
        ]
    st.pydeck_chart(
        pdk.Deck(
            layers=layers,
            initial_view_state=view_for(rows, focus, location),
            map_provider="carto",
            # Carto "Dark Matter" without place names: the basemap's district
            # names clashed with ours. Territory names show on hover.
            map_style="dark_no_labels",
            # Shown by the browser itself (no server round trip): name + points.
            tooltip={"html": TOOLTIP_HTML, "style": TOOLTIP_STYLE},
        ),
        height=600,
        key=f"territory_map:{context}",
    )


def territory_list(rows: list[dict]) -> None:
    """The same information as the map, as a table (SCREENS.md: map alternative)."""
    order = {"yours": 0, "theirs": 1, "free": 2}
    st.dataframe(
        [
            {"Territory": row["name"], "Status": LEGEND[row["status"]], "Owner": row["owner"],
             "Your points": row["my_points"], "What it means": row["detail"]}
            for row in sorted(rows, key=lambda r: (order[r["status"]], r["name"]))
        ],
        hide_index=True,
        width="stretch",
    )
