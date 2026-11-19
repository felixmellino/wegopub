"""Checks that data/territories.geojson follows R-T01 and R-T02 in
docs/ontology/RULES.md, that the app's loader reads it, that it is copied
into the database correctly, and that the app's own location matcher
assigns real places to the right territory.

Overlap is measured in metres: hand-drawn shared borders are snapped
together, so two neighbours can disagree by a centimetre at their common
edge. That is fine. Any spot lying more than OVERLAP_TOLERANCE_M inside
two territories is a real overlap and fails the test.
"""

import json
import math

import pytest

import data.db as db
from core.location import evaluate_location, point_in_polygon
from data.territory_file import TERRITORY_FILE, load_territories

# Metres per degree at Lisbon's latitude (about 38.7° N).
METRES_PER_DEG_LNG = 86_900
METRES_PER_DEG_LAT = 110_574

OVERLAP_TOLERANCE_M = 0.5
SAMPLE_STEP_M = 2.0

# Rough box around Lisbon and Carcavelos (Nova SBE), as (lng, lat) like
# GeoJSON. Catches swapped coordinates, which would land in Ethiopia.
LISBON_LNG = (-9.40, -9.05)
LISBON_LAT = (38.65, 38.80)


def load_features():
    with open(TERRITORY_FILE, encoding="utf-8") as f:
        collection = json.load(f)
    assert collection["type"] == "FeatureCollection"
    return collection["features"]


def outer_ring(feature):
    return feature["geometry"]["coordinates"][0]


def distance_to_edge_m(lng, lat, ring):
    """Shortest distance in metres from a point to the outline of `ring`."""
    px, py = lng * METRES_PER_DEG_LNG, lat * METRES_PER_DEG_LAT
    best = math.inf
    for (ax, ay), (bx, by) in zip(ring, ring[1:]):
        ax, ay = ax * METRES_PER_DEG_LNG, ay * METRES_PER_DEG_LAT
        bx, by = bx * METRES_PER_DEG_LNG, by * METRES_PER_DEG_LAT
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        t = 0.0 if length_sq == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
        best = min(best, math.hypot(px - (ax + t * dx), py - (ay + t * dy)))
    return best


def _boundary_samples(ring):
    """Every corner plus a point every SAMPLE_STEP_M metres along each edge."""
    for (ax, ay), (bx, by) in zip(ring, ring[1:]):
        length_m = math.hypot((bx - ax) * METRES_PER_DEG_LNG, (by - ay) * METRES_PER_DEG_LAT)
        steps = max(1, int(length_m // SAMPLE_STEP_M))
        for i in range(steps):
            t = i / steps
            yield ax + (bx - ax) * t, ay + (by - ay) * t


def _deepest_into(ring_a, ring_b):
    """How far ring_a's outline reaches inside ring_b, in metres."""
    lngs, lats = [p[0] for p in ring_b], [p[1] for p in ring_b]
    box = (min(lngs), max(lngs), min(lats), max(lats))
    deepest = 0.0
    for lng, lat in _boundary_samples(ring_a):
        if box[0] < lng < box[1] and box[2] < lat < box[3] and point_in_polygon(lat, lng, ring_b):
            deepest = max(deepest, distance_to_edge_m(lng, lat, ring_b))
    return deepest


def deepest_overlap_m(ring_a, ring_b):
    """How far (in metres) two outlines reach into each other. 0 means they
    don't overlap. If two areas overlap, part of one outline must lie inside
    the other (or one sits completely inside the other), so checking points
    along both outlines is enough, and fast even for very large areas."""
    lng_min = max(min(p[0] for p in ring_a), min(p[0] for p in ring_b))
    lng_max = min(max(p[0] for p in ring_a), max(p[0] for p in ring_b))
    lat_min = max(min(p[1] for p in ring_a), min(p[1] for p in ring_b))
    lat_max = min(max(p[1] for p in ring_a), max(p[1] for p in ring_b))
    if lng_min >= lng_max or lat_min >= lat_max:
        return 0.0  # bounding boxes don't even touch
    return max(_deepest_into(ring_a, ring_b), _deepest_into(ring_b, ring_a))


# -- R-T01: every territory is a named, closed polygon in Lisbon --------------

def test_file_has_the_forty_eight_territories():
    assert len(load_features()) == 48


def test_app_loader_reads_every_territory_with_its_permanent_id():
    """The real loader the app uses accepts the file (it raises on any
    R-T01 problem) and keeps each territory's id from the file."""
    territories = load_territories()
    file_ids = [f["properties"]["id"] for f in load_features()]
    assert [t.id for t in territories] == file_ids
    assert len(set(file_ids)) == 48


def test_every_territory_has_a_unique_name():
    names = [f["properties"].get("name", "").strip() for f in load_features()]
    assert all(names), "a territory is missing its name"
    assert len(names) == len(set(names)), "two territories share a name"


def test_every_territory_is_a_closed_polygon():
    for feature in load_features():
        name = feature["properties"]["name"]
        assert feature["geometry"]["type"] == "Polygon", name
        ring = outer_ring(feature)
        assert len(ring) >= 4, f"{name} needs at least 3 corners"
        assert ring[0] == ring[-1], f"{name}'s outline is not closed"


def test_coordinates_are_lng_lat_inside_lisbon():
    for feature in load_features():
        for lng, lat in outer_ring(feature):
            assert LISBON_LNG[0] < lng < LISBON_LNG[1], feature["properties"]["name"]
            assert LISBON_LAT[0] < lat < LISBON_LAT[1], feature["properties"]["name"]


# -- R-T02: territories may touch but never overlap ------------------------

def test_no_two_territories_overlap():
    features = load_features()
    for i, a in enumerate(features):
        for b in features[i + 1:]:
            depth = deepest_overlap_m(outer_ring(a), outer_ring(b))
            assert depth <= OVERLAP_TOLERANCE_M, (
                f"{a['properties']['name']} and {b['properties']['name']} "
                f"overlap by {depth:.1f} m"
            )


def test_overlap_check_catches_a_real_overlap():
    """Rejected case: proves the check above would actually fail on a bad file."""
    square = [[-9.1450, 38.7120], [-9.1440, 38.7120], [-9.1440, 38.7130], [-9.1450, 38.7130], [-9.1450, 38.7120]]
    shifted = [[lng + 0.0005, lat] for lng, lat in square]  # half-way over
    assert deepest_overlap_m(square, shifted) > OVERLAP_TOLERANCE_M


def test_overlap_check_allows_a_shared_border():
    """Boundary case: two squares sharing one edge are allowed."""
    left = [[-9.1450, 38.7120], [-9.1440, 38.7120], [-9.1440, 38.7130], [-9.1450, 38.7130], [-9.1450, 38.7120]]
    right = [[lng + 0.0010, lat] for lng, lat in left]  # starts exactly where `left` ends
    assert deepest_overlap_m(left, right) <= OVERLAP_TOLERANCE_M


# -- Real places land where they should ----------------------------------

@pytest.mark.parametrize(
    "place, lat_lng, expected_name",
    [
        ("Jardim do Alto de Santa Catarina", (38.70963, -9.14765), "Santa Catarina"),
        ("K Urban Beach Club", (38.70386, -9.15543), "After8"),
        ("Rua da Rosa, middle", (38.7133, -9.1456), "Shortys"),
        ("Nova SBE main building", (38.6782, -9.3259), "Nova SBE Campus"),
        ("Carcavelos beach, part of the Nova area", (38.6790, -9.3360), "Nova SBE Campus"),
        ("Largo de Camões", (38.71057, -9.14343), "Chiado"),
        ("Praça do Comércio", (38.7075, -9.1365), "Baixa"),
        ("Mosteiro dos Jerónimos", (38.6979, -9.2068), "Belém"),
        ("Jamor golf course", (38.7134, -9.2540), "Jamor Golf"),
        ("Jardim do Príncipe Real", (38.71628, -9.14861), "Príncipe Real"),
        ("Rua Nova do Carvalho", (38.70723, -9.14380), "Pink Street"),
    ],
)
def test_known_places_match_their_territory(place, lat_lng, expected_name):
    territories = load_territories()
    result, territory_id = evaluate_location(lat_lng, None, territories)
    assert result == "matched", place
    assert next(t.name for t in territories if t.id == territory_id) == expected_name


def test_the_airport_is_outside_every_territory():
    """Outside case (R1): beyond the covered area a drink counts for the season only."""
    result, territory_id = evaluate_location((38.7742, -9.1342), None, load_territories())
    assert result == "outside"
    assert territory_id is None


# -- Copying the file into the database ----------------------------------

class FakeTable:
    def __init__(self):
        self.upserted = None

    def upsert(self, rows):
        self.upserted = rows
        return self

    def execute(self):
        return self


class FakeClient:
    def __init__(self):
        self.tables = {}

    def table(self, name):
        return self.tables.setdefault(name, FakeTable())


def test_upsert_territories_sends_id_name_and_outline(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(db, "get_client", lambda: client)
    territories = load_territories()

    db.upsert_territories(territories)

    rows = client.tables["territories"].upserted
    assert [row["id"] for row in rows] == [t.id for t in territories]
    assert rows[0] == {"id": territories[0].id, "name": territories[0].name, "boundary": territories[0].boundary}
    assert set(rows[0]["boundary"]) == {"type", "coordinates"}  # no geojson.io colours in the database


def test_upsert_territories_with_nothing_to_copy_does_not_call_the_database(monkeypatch):
    def fail():
        raise AssertionError("database should not be called")

    monkeypatch.setattr(db, "get_client", fail)
    db.upsert_territories([])


# -- The app notices when the territory file changes --------------------------

def test_file_version_changes_with_the_contents(tmp_path):
    from data.territory_file import territory_file_version
    path = tmp_path / "territories.geojson"
    path.write_text('{"type": "FeatureCollection", "features": []}')
    first = territory_file_version(path)
    assert territory_file_version(path) == first
    path.write_text('{"type": "FeatureCollection", "features": [ ]}')
    assert territory_file_version(path) != first


def test_new_file_version_is_loaded_and_copied_again(monkeypatch):
    """A merge that edits the file must reach the app without a restart."""
    import shared
    shared._load_and_sync.clear()
    copies, version = [], {"now": "v1"}
    monkeypatch.setattr(shared, "territory_file_version", lambda: version["now"])
    monkeypatch.setattr(shared, "load_territories", lambda: [version["now"]])
    monkeypatch.setattr(db, "upsert_territories", lambda territories: copies.append(list(territories)))

    assert shared.get_territories() == ["v1"]
    assert shared.get_territories() == ["v1"]
    assert copies == [["v1"]]  # same file: loaded and copied once

    version["now"] = "v2"
    assert shared.get_territories() == ["v2"]
    assert copies == [["v1"], ["v2"]]  # changed file: picked up by itself
    shared._load_and_sync.clear()
