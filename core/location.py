"""Matching the phone's GPS reading to a territory (R-L01 to R-L04).

location_check_result meanings:
- "unavailable": no phone GPS reading at all.
- "uncertain": the phone says its reading may be off by more than
  MAX_GPS_ACCURACY_M (R-L02), or the point lies in more than one territory
  (overlapping outlines; R-T02 and its test prevent this).
- "matched": the point lies inside exactly one territory. Being close to a
  border does not matter (R-L03).
- "outside": the point lies inside no territory.

Photo GPS is not used (R-L01).
"""

from __future__ import annotations

import math

from core.constants import MAX_GPS_ACCURACY_M, MAX_GPS_AGE_SECONDS
from core.models import Territory

GPS = tuple[float, float]  # (lat, lng)

BROWSER_LOCATION_ERRORS = {"denied", "unavailable", "timeout", "unsupported"}


def parse_phone_reading(
    value: object, now_ms: float | None = None
) -> tuple[GPS | None, float | None, str | None]:
    """Check the newest reading the automatic phone tracker sent.

    Returns (device_gps, accuracy_m, problem). On success problem is None.
    Otherwise device_gps and accuracy_m are None and problem is one of:
    "waiting" (no reading yet), "denied", "unavailable", "timeout",
    "unsupported" (reported by the browser), "stale" (older than
    MAX_GPS_AGE_SECONDS, R-L04), or "invalid" (anything malformed, so a
    tampered request can't inject a location).

    `now_ms` is the current time in milliseconds since 1970. The app always
    passes it; tests that don't care about age may leave it out."""
    if value is None:
        return None, None, "waiting"
    if not isinstance(value, dict):
        return None, None, "invalid"
    if "error" in value:
        error = value["error"]
        return None, None, error if error in BROWSER_LOCATION_ERRORS else "invalid"

    lat, lng, accuracy = value.get("lat"), value.get("lng"), value.get("accuracy_m")
    numbers = (lat, lng, accuracy)
    if not all(isinstance(n, (int, float)) and not isinstance(n, bool) for n in numbers):
        return None, None, "invalid"
    if not (-90 <= lat <= 90 and -180 <= lng <= 180 and accuracy >= 0):
        return None, None, "invalid"
    if now_ms is not None:
        taken_at = value.get("taken_at_ms")
        if not isinstance(taken_at, (int, float)) or isinstance(taken_at, bool) or not math.isfinite(taken_at):
            return None, None, "invalid"
        age_seconds = (now_ms - taken_at) / 1000
        if age_seconds < -MAX_GPS_AGE_SECONDS:  # far in the future: phone clock or tampering
            return None, None, "invalid"
        if age_seconds > MAX_GPS_AGE_SECONDS:
            return None, None, "stale"
    return (float(lat), float(lng)), float(accuracy), None


def point_in_polygon(lat: float, lng: float, polygon_coords: list[list[float]]) -> bool:
    """Ray-casting point-in-polygon test over a GeoJSON exterior ring
    (a list of [lng, lat] pairs). Does not support holes."""
    inside = False
    n = len(polygon_coords)
    j = n - 1
    for i in range(n):
        xi, yi = polygon_coords[i][0], polygon_coords[i][1]
        xj, yj = polygon_coords[j][0], polygon_coords[j][1]
        if ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / (yj - yi) + xi
        ):
            inside = not inside
        j = i
    return inside


def find_matching_territories(lat: float, lng: float, territories: list[Territory]) -> list[Territory]:
    matches = []
    for territory in territories:
        ring = territory.boundary["coordinates"][0]
        if point_in_polygon(lat, lng, ring):
            matches.append(territory)
    return matches


def evaluate_location(
    device_gps: GPS | None,
    accuracy_m: float | None,
    territories: list[Territory],
) -> tuple[str, str | None]:
    """Return (location_check_result, territory_id).

    `accuracy_m` is how many metres the phone says its reading may be off.
    The Check-in page always passes the accuracy the phone reported (see
    parse_phone_reading); None is only used by tests that don't care about
    accuracy. A territory id is only returned for
    "matched", so an uncertain reading never silently gets a territory."""
    if device_gps is None:
        return "unavailable", None
    if accuracy_m is not None and accuracy_m > MAX_GPS_ACCURACY_M:
        return "uncertain", None

    matches = find_matching_territories(device_gps[0], device_gps[1], territories)
    if len(matches) > 1:
        return "uncertain", None
    if len(matches) == 1:
        return "matched", matches[0].id
    return "outside", None
