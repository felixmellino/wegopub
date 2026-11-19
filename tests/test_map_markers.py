"""Owner badges group only neighbours; they never merge territory accounts."""
import base64
from io import BytesIO

from PIL import Image

from core.location import point_in_polygon
from map_markers import adjacent, area, badge_image, interior_anchor, owner_markers
from map_ui import COLOURS


def polygon(x=0, y=0, width=0.001):
    x, y = -9.14 + x, 38.71 + y
    return {"type": "Polygon", "coordinates": [[[x, y], [x + width, y],
            [x + width, y + width], [x, y + width], [x, y]]]}


def row(id_, boundary, owner="a", name="Alex Smith"):
    return {"id": id_, "name": id_, "owner_id": owner, "owner": name,
            "status": "yours" if owner == "a" else "theirs", "boundary": boundary}


def test_transitive_neighbours_group_but_separate_accounts_and_unclaimed_do_not():
    rows = [row("a", polygon()), row("b", polygon(.001)), row("c", polygon(.002)),
            row("d", polygon(.003), owner="b"),  # Same display name, distinct owner.
            row("e", polygon(.006)), row("f", polygon(.007), owner=None)]
    markers = owner_markers(rows, {}, COLOURS)
    assert sorted(sorted(m["territory_ids"]) for m in markers) == [["a", "b", "c"], ["d"], ["e"]]
    assert all(m["initials"] == "AS" for m in markers)
    group = next(m for m in markers if len(m["territory_ids"]) == 3)
    assert any(point_in_polygon(group["position"][1], group["position"][0], r["boundary"]["coordinates"][0])
               for r in rows[:3])


def test_adjacency_rejects_corner_contact_and_street_gaps():
    assert adjacent(polygon(), polygon(.001))
    assert not adjacent(polygon(), polygon(.001, .001))
    assert not adjacent(polygon(), polygon(.00102))  # ~1.7 m gap.
    assert adjacent(polygon(), polygon(.001003))  # Hand-drawn sub-half-metre mismatch.
    split = polygon(.001)
    split["coordinates"][0].insert(-1, [-9.139, 38.7105])
    assert adjacent(polygon(), split)


def test_smaller_areas_have_smaller_badges_and_large_ones_are_capped():
    sizes = []
    for width in (.0001, .001, .01):
        marker = owner_markers([row("a", polygon(width=width))], {}, COLOURS)[0]
        sizes.append(marker["size"])
    assert sizes[0] < sizes[1] < sizes[2] <= 120
    assert area(polygon(width=.001)) > area(polygon(width=.0001))


def test_concave_area_gets_an_inside_anchor():
    shape = polygon()
    x, y = -9.14, 38.71
    shape["coordinates"] = [[[x, y], [x+.003, y], [x+.003, y+.001], [x+.001, y+.001],
                             [x+.001, y+.003], [x, y+.003], [x, y]]]
    position, clearance = interior_anchor(shape)
    assert point_in_polygon(position[1], position[0], shape["coordinates"][0])
    assert clearance > 0


def test_badge_has_transparent_corners_and_blurred_photo_with_safe_fallback():
    source = Image.new("RGB", (96, 96), "white")
    for x in range(48):
        for y in range(96):
            source.putpixel((x, y), (0, 0, 0))
    photo = BytesIO()
    source.save(photo, format="PNG")
    def decode(raw):
        return Image.open(BytesIO(base64.b64decode(badge_image(raw, COLOURS["yours"]).split(",")[1])))
    image = decode(photo.getvalue())
    assert image.getpixel((0, 0))[3] == 0
    assert 20 < image.getpixel((47, 48))[0] < 160  # Blended edge rather than sharp black/white.
    assert decode(b"invalid photo").getpixel((48, 48))[3] == 255
