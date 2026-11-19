from datetime import datetime

import pytest

from core.models import DrinkEntry
from core.territories import capture_status, parse_territories, replay_leader, territory_owner, territory_standings

TERRITORY_ID = "territory-a"


def make_entry(id_, membership_id, points, ts, territory_id=TERRITORY_ID, result="matched"):
    return DrinkEntry(
        id=id_,
        membership_id=membership_id,
        season_id="season-1",
        drink_type="shot",
        amount=None,
        photo_ref="photo",
        device_gps=None,
        photo_gps=None,
        territory_id=territory_id,
        location_check_result=result,
        points_awarded=points,
        submitted_at=ts,
    )


def test_replay_leader_tie_does_not_displace_current_leader():
    events = [
        (datetime(2026, 11, 19, 20, 0), "A", 10),
        (datetime(2026, 11, 19, 20, 5), "B", 10),  # ties A, A stays leader
    ]
    assert replay_leader(events) == "A"


def test_replay_leader_strict_overtake_flips_leader():
    events = [
        (datetime(2026, 11, 19, 20, 0), "A", 10),
        (datetime(2026, 11, 19, 20, 5), "B", 10),  # tie, A stays
        (datetime(2026, 11, 19, 20, 10), "B", 1),  # B now strictly ahead
    ]
    assert replay_leader(events) == "B"


def test_territory_owner_changes_hands_on_overtake():
    entries = [
        make_entry("e1", "A", 10, datetime(2026, 11, 19, 20, 0)),
        make_entry("e2", "B", 10, datetime(2026, 11, 19, 20, 5)),
    ]
    assert territory_owner(entries, TERRITORY_ID) == "A"  # tie -> A keeps it

    entries.append(make_entry("e3", "B", 1, datetime(2026, 11, 19, 20, 10)))
    assert territory_owner(entries, TERRITORY_ID) == "B"  # overtake -> B owns it


def test_only_matched_entries_count_toward_territory():
    entries = [
        make_entry("e1", "A", 10, datetime(2026, 11, 19, 20, 0)),
        make_entry("e2", "B", 100, datetime(2026, 11, 19, 20, 5), result="uncertain"),
    ]
    # B's entry is "uncertain", not "matched" -- doesn't count here.
    assert territory_owner(entries, TERRITORY_ID) == "A"


def test_territory_standings_sorted_descending():
    entries = [
        make_entry("e1", "A", 10, datetime(2026, 11, 19, 20, 0)),
        make_entry("e2", "B", 25, datetime(2026, 11, 19, 20, 5)),
    ]
    standings = territory_standings(entries, TERRITORY_ID)
    assert standings[0] == ("B", 25)
    assert standings[1] == ("A", 10)


# -- parse_territories: reading the territory file (R-T01) -----------------

SQUARE = [[-9.145, 38.712], [-9.144, 38.712], [-9.144, 38.713], [-9.145, 38.713], [-9.145, 38.712]]
GOOD_ID = "rua-da-rosa"
OTHER_ID = "le-pub"


def make_feature(name="Rua da Rosa", id_=GOOD_ID, ring=SQUARE, geometry_type="Polygon", **extra):
    return {
        "type": "Feature",
        "properties": {"id": id_, "name": name, **extra},
        "geometry": {"type": geometry_type, "coordinates": [ring]},
    }


def collection(*features):
    return {"type": "FeatureCollection", "features": list(features)}


def test_parse_territories_reads_id_name_and_outline():
    [territory] = parse_territories(collection(make_feature(fill="#e6194b")))
    assert territory.id == GOOD_ID
    assert territory.name == "Rua da Rosa"
    assert territory.boundary == {"type": "Polygon", "coordinates": [SQUARE]}  # colours dropped


@pytest.mark.parametrize(
    "feature, message",
    [
        (make_feature(name="  "), "no name"),
        (make_feature(id_=None), "short id"),
        (make_feature(id_=""), "short id"),
        (make_feature(id_="Rua da Rosa"), "short id"),
        (make_feature(id_="rua_da_rosa"), "short id"),
        (make_feature(id_="-rua-da-rosa"), "short id"),
        (make_feature(id_="rua--da-rosa"), "short id"),
        (make_feature(id_=7), "short id"),
        (make_feature(geometry_type="LineString"), "must be a Polygon"),
        (make_feature(ring=SQUARE[:-1]), "closed outline"),
        (make_feature(ring=[SQUARE[0], SQUARE[1], SQUARE[0]]), "closed outline"),
    ],
)
def test_parse_territories_rejects_broken_territories(feature, message):
    with pytest.raises(ValueError, match=message):
        parse_territories(collection(feature))


@pytest.mark.parametrize("id_", ["after8", "rua-da-rosa", "t1"])
def test_parse_territories_accepts_short_readable_ids(id_):
    [territory] = parse_territories(collection(make_feature(id_=id_)))
    assert territory.id == id_


def test_parse_territories_rejects_duplicate_ids():
    with pytest.raises(ValueError, match="same id"):
        parse_territories(collection(make_feature(name="A"), make_feature(name="B")))


def test_parse_territories_rejects_duplicate_names():
    with pytest.raises(ValueError, match="same name"):
        parse_territories(collection(make_feature(id_=GOOD_ID), make_feature(id_=OTHER_ID)))


def test_parse_territories_rejects_a_non_collection():
    with pytest.raises(ValueError, match="FeatureCollection"):
        parse_territories({"type": "Feature"})


# -- capture_status: what the map tells you about a territory ----------------

def test_unclaimed_territory_is_free():
    assert capture_status([], None, "me") == ("free", 0)


def test_you_own_it_and_lead_by_the_gap_to_the_runner_up():
    assert capture_status([("me", 7), ("B", 4)], "me", "me") == ("yours", 3)


def test_you_own_it_alone_and_lead_by_all_your_points():
    assert capture_status([("me", 5)], "me", "me") == ("yours", 5)


def test_you_own_it_after_a_tie_and_lead_by_zero():
    """R-R01: whoever reached the tie first keeps it."""
    assert capture_status([("me", 4), ("B", 4)], "me", "me") == ("yours", 0)


def test_someone_else_owns_it_you_need_one_more_than_the_gap():
    assert capture_status([("B", 6), ("me", 2)], "B", "me") == ("theirs", 5)


def test_you_have_no_points_there_yet():
    assert capture_status([("B", 3)], "B", "me") == ("theirs", 4)


def test_tied_but_not_owner_needs_one_point():
    assert capture_status([("B", 4), ("me", 4)], "B", "me") == ("theirs", 1)
