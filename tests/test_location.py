import pytest

from core.location import evaluate_location, parse_phone_reading
from core.models import Territory

TERRITORY = Territory(
    id="territory-a",
    name="Bairro Alto",
    boundary={
        "type": "Polygon",
        "coordinates": [
            [[-9.15, 38.70], [-9.14, 38.70], [-9.14, 38.71], [-9.15, 38.71], [-9.15, 38.70]]
        ],
    },
)
INSIDE = (38.705, -9.145)  # lat, lng -- inside TERRITORY
NEAR_EDGE = (38.705, -9.1401)  # inside TERRITORY, about 9 m from its east border
OUTSIDE = (38.80, -9.00)  # far away, outside every territory


def test_matched_when_inside_and_accuracy_is_good():
    result, territory_id = evaluate_location(INSIDE, 10.0, [TERRITORY])
    assert result == "matched"
    assert territory_id == TERRITORY.id


def test_matched_when_no_accuracy_is_reported():
    """Manual coordinates report no accuracy; accepted until real GPS."""
    result, territory_id = evaluate_location(INSIDE, None, [TERRITORY])
    assert result == "matched"
    assert territory_id == TERRITORY.id


def test_exactly_50_m_accuracy_is_accepted():
    """Boundary case of R-L02."""
    result, _ = evaluate_location(INSIDE, 50.0, [TERRITORY])
    assert result == "matched"


def test_worse_than_50_m_accuracy_is_uncertain_without_a_territory():
    """Rejected case of R-L02: no territory is assigned silently."""
    result, territory_id = evaluate_location(INSIDE, 50.1, [TERRITORY])
    assert result == "uncertain"
    assert territory_id is None


def test_point_near_a_border_belongs_to_the_territory_it_is_in():
    """R-L03: the accuracy circle (40 m) crosses the border, the point decides."""
    result, territory_id = evaluate_location(NEAR_EDGE, 40.0, [TERRITORY])
    assert result == "matched"
    assert territory_id == TERRITORY.id


def test_outside_every_territory():
    result, territory_id = evaluate_location(OUTSIDE, 10.0, [TERRITORY])
    assert result == "outside"
    assert territory_id is None


def test_unavailable_when_no_phone_gps():
    result, territory_id = evaluate_location(None, 10.0, [TERRITORY])
    assert result == "unavailable"
    assert territory_id is None


def test_overlapping_territories_are_uncertain():
    """Defensive: R-T02 forbids overlap, but if it happens, assign nothing."""
    twin = Territory(id="territory-b", name="Twin", boundary=TERRITORY.boundary)
    result, territory_id = evaluate_location(INSIDE, 10.0, [TERRITORY, twin])
    assert result == "uncertain"
    assert territory_id is None


# -- parse_phone_reading: what the automatic phone tracker sends ----------

def test_phone_reading_is_turned_into_gps_and_accuracy():
    gps, accuracy, problem = parse_phone_reading({"lat": 38.7133, "lng": -9.1456, "accuracy_m": 12})
    assert gps == (38.7133, -9.1456)
    assert accuracy == 12.0
    assert problem is None


def test_no_reading_yet():
    assert parse_phone_reading(None) == (None, None, "waiting")


@pytest.mark.parametrize("error", ["denied", "unavailable", "timeout", "unsupported"])
def test_browser_errors_are_passed_on(error):
    assert parse_phone_reading({"error": error}) == (None, None, error)


@pytest.mark.parametrize(
    "value",
    [
        "38.7,-9.1",
        {"error": "hacked"},
        {"lat": "38.7", "lng": -9.1, "accuracy_m": 10},
        {"lat": 38.7, "lng": -9.1},
        {"lat": 38.7, "lng": -9.1, "accuracy_m": True},
        {"lat": 91, "lng": -9.1, "accuracy_m": 10},
        {"lat": 38.7, "lng": -181, "accuracy_m": 10},
        {"lat": 38.7, "lng": -9.1, "accuracy_m": -1},
        {"lat": float("nan"), "lng": -9.1, "accuracy_m": 10},
    ],
    ids=["text", "unknown-error", "lat-as-text", "no-accuracy", "accuracy-bool",
         "lat-too-big", "lng-too-small", "negative-accuracy", "lat-nan"],
)
def test_malformed_readings_are_rejected(value):
    """Input validation: a tampered or broken reading never becomes a location."""
    assert parse_phone_reading(value) == (None, None, "invalid")


def test_phone_reading_flows_into_the_location_check():
    gps, accuracy, _ = parse_phone_reading({"lat": INSIDE[0], "lng": INSIDE[1], "accuracy_m": 30})
    assert evaluate_location(gps, accuracy, [TERRITORY]) == ("matched", TERRITORY.id)
    gps, accuracy, _ = parse_phone_reading({"lat": INSIDE[0], "lng": INSIDE[1], "accuracy_m": 80})
    assert evaluate_location(gps, accuracy, [TERRITORY]) == ("uncertain", None)


# -- R-L04: a reading may be at most 60 seconds old --------------------

NOW_MS = 1_800_000_000_000
FRESH = {"lat": INSIDE[0], "lng": INSIDE[1], "accuracy_m": 10}


@pytest.mark.parametrize("age_seconds", [0, 30, 60])
def test_reading_up_to_60_seconds_old_is_used(age_seconds):
    reading = {**FRESH, "taken_at_ms": NOW_MS - age_seconds * 1000}
    assert parse_phone_reading(reading, now_ms=NOW_MS)[2] is None


def test_reading_older_than_60_seconds_is_stale():
    reading = {**FRESH, "taken_at_ms": NOW_MS - 60_001}
    assert parse_phone_reading(reading, now_ms=NOW_MS) == (None, None, "stale")


@pytest.mark.parametrize("taken_at", [None, "now", True, float("nan"), NOW_MS + 61_000])
def test_missing_or_impossible_reading_time_is_invalid(taken_at):
    reading = {**FRESH, "taken_at_ms": taken_at}
    assert parse_phone_reading(reading, now_ms=NOW_MS) == (None, None, "invalid")


def test_slightly_fast_phone_clock_is_tolerated():
    reading = {**FRESH, "taken_at_ms": NOW_MS + 5_000}
    assert parse_phone_reading(reading, now_ms=NOW_MS)[2] is None
