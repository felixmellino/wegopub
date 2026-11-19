"""Display-only geometry and circular owner pictures for the territory map.

Coordinates are projected to local metres around Lisbon. Grouping changes
only badges: ownership, scores and each territory's outline stay separate.
"""
from __future__ import annotations

import base64
import math
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from core.location import point_in_polygon
from core.profile_photo import initials

LNG_M = 86_900
LAT_M = 110_574
BORDER_TOLERANCE_M = 0.5  # Same hand-drawn border tolerance as territory data QA.


def _ring(boundary):
    return [(p[0] * LNG_M, p[1] * LAT_M) for p in boundary["coordinates"][0]]


def area(boundary):
    ring = _ring(boundary)
    # Translate before multiplying to avoid cancellation with world coordinates.
    ox, oy = ring[0]
    return abs(sum((a[0] - ox) * (b[1] - oy) - (b[0] - ox) * (a[1] - oy)
                   for a, b in zip(ring, ring[1:]))) / 2


def adjacent(first, second):
    """Shared border of >0.5 m; corner-only contact and street gaps don't group.

    Projecting segment endpoints also handles a shared edge split into
    different numbers of vertices in the two hand-drawn polygons.
    """
    for a, b in zip(_ring(first), _ring(first)[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length <= BORDER_TOLERANCE_M:
            continue
        for c, d in zip(_ring(second), _ring(second)[1:]):
            distances = [abs(dx * (p[1] - a[1]) - dy * (p[0] - a[0])) / length for p in (c, d)]
            if max(distances) > BORDER_TOLERANCE_M:
                continue
            positions = [((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length for p in (c, d)]
            overlap = min(length, max(positions)) - max(0, min(positions))
            if overlap > BORDER_TOLERANCE_M:
                return True
    return False


def interior_anchor(boundary):
    """Choose an inside point with room for a badge, even in a concave area."""
    ring = _ring(boundary)
    left, right = min(p[0] for p in ring), max(p[0] for p in ring)
    bottom, top = min(p[1] for p in ring), max(p[1] for p in ring)
    candidates = [(left + (right - left) * (x + .5) / 20,
                   bottom + (top - bottom) * (y + .5) / 20)
                  for x in range(20) for y in range(20)]
    best, clearance = None, -1
    for x, y in candidates:
        if not point_in_polygon(y / LAT_M, x / LNG_M, boundary["coordinates"][0]):
            continue
        distance = math.inf
        for a, b in zip(ring, ring[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            squared = dx * dx + dy * dy
            t = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / squared)) if squared else 0
            distance = min(distance, math.hypot(x - a[0] - t * dx, y - a[1] - t * dy))
        if distance > clearance:
            best, clearance = (x, y), distance
    if best is None:
        # Very thin polygons may miss the grid. An edge midpoint is on the area.
        a, b = max(zip(ring, ring[1:]), key=lambda edge: math.dist(*edge))
        best = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        clearance = 0
    return [best[0] / LNG_M, best[1] / LAT_M], clearance


def badge_image(photo, colour):
    """Blur and darken authorized photo bytes, with a transparent circular crop.

    Initials are a separate map text layer so they stay crisp at every zoom.
    No photo bytes are cached; revoked access takes effect on the next render.
    """
    image = Image.new("RGB", (96, 96), (32, 46, 61))
    if photo:
        try:
            with Image.open(BytesIO(photo)) as source:
                image = ImageOps.fit(source.convert("RGB"), (96, 96)).filter(ImageFilter.GaussianBlur(5))
            image = Image.blend(image, Image.new("RGB", image.size, (15, 23, 35)), .4)
        except (OSError, ValueError, Image.DecompressionBombError):
            pass
    image = image.convert("RGBA")
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).ellipse((2, 2, 94, 94), fill=255)
    image.putalpha(mask)
    ImageDraw.Draw(image).ellipse((3, 3, 93, 93), outline=tuple(colour) + (255,), width=4)
    output = BytesIO()
    image.save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def owner_markers(rows, pictures, colours):
    """One badge for each connected group belonging to the same stable owner id."""
    pending = {row["id"]: row for row in rows if row.get("owner_id")}
    markers = []
    while pending:
        _, first = pending.popitem()
        group, queue = [first], [first]
        while queue:
            current = queue.pop()
            for key, candidate in list(pending.items()):
                if candidate["owner_id"] == first["owner_id"] and adjacent(current["boundary"], candidate["boundary"]):
                    group.append(pending.pop(key))
                    queue.append(candidate)
        group.sort(key=lambda row: row["id"])
        areas = [area(row["boundary"]) for row in group]
        anchors = [interior_anchor(row["boundary"]) for row in group]
        total = sum(areas) or 1
        centre = [sum(anchor[0][axis] * weight for anchor, weight in zip(anchors, areas)) / total
                  for axis in (0, 1)]
        # Keep the badge inside an actual territory, never in a concave group's gap.
        position, clearance = min(anchors, key=lambda item: math.hypot(
            (item[0][0] - centre[0]) * LNG_M, (item[0][1] - centre[1]) * LAT_M))
        diameter = max(3, min(120, math.sqrt(total) * .35, clearance * 1.5))
        markers.append({
            "territory_ids": [row["id"] for row in group],
            "position": position, "size": diameter, "text_size": diameter * .3,
            "initials": initials(first["owner"]),
            "icon": {"url": badge_image(pictures.get(first["owner_id"]), colours[first["status"]]),
                     "width": 96, "height": 96, "anchorY": 48},
            "name": first["owner"],
            "detail": f"{len(group)} territories · Tap to view points" if len(group) > 1 else "Tap to view territory points",
            "points": "",
        })
    return markers
