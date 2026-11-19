"""Read the location evidence and prepare a camera photo for private storage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import BytesIO
from math import isfinite
from warnings import catch_warnings, simplefilter

from PIL import ExifTags, Image, ImageOps

from core.constants import PHOTO_RETENTION_DAYS

MAX_PHOTO_BYTES = 10 * 1024 * 1024
MAX_PHOTO_PIXELS = 20_000_000


def photo_expires_at(season_ends_at: datetime) -> datetime:
    """Legacy season times without an offset are interpreted as UTC."""
    if season_ends_at.tzinfo is None:
        season_ends_at = season_ends_at.replace(tzinfo=timezone.utc)
    return season_ends_at.astimezone(timezone.utc) + timedelta(days=PHOTO_RETENTION_DAYS)


class InvalidCheckinPhoto(ValueError):
    """The camera image could not be decoded safely."""


def _photo_gps(image: Image.Image) -> tuple[float, float] | None:
    try:
        gps = image.getexif().get_ifd(ExifTags.IFD.GPSInfo)
        if gps[1] not in ("N", "S") or gps[3] not in ("E", "W"):
            return None
        lat = _decimal_degrees(gps[2], gps[1])
        lng = _decimal_degrees(gps[4], gps[3])
        if isfinite(lat) and isfinite(lng) and abs(lat) <= 90 and abs(lng) <= 180:
            return lat, lng
    except (KeyError, OSError, TypeError, ValueError, OverflowError, ZeroDivisionError):
        # Phone cameras can omit GPS or supply incomplete metadata.
        pass
    return None


def _decimal_degrees(value, direction: str) -> float:
    degrees, minutes, seconds = value
    decimal = float(degrees + minutes / 60 + seconds / 3600)
    return -decimal if direction in ("S", "W") else decimal


def prepare_checkin_photo(camera_bytes: bytes) -> tuple[tuple[float, float] | None, bytes]:
    """Return optional GPS evidence and a JPEG containing only image pixels."""
    if len(camera_bytes) > MAX_PHOTO_BYTES:
        raise InvalidCheckinPhoto("Take a smaller photo. The upload limit is 10 MB.")
    output = BytesIO()
    try:
        with catch_warnings():
            simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(camera_bytes), formats=("JPEG",)) as original:
                if original.width * original.height > MAX_PHOTO_PIXELS:
                    raise InvalidCheckinPhoto("Take a smaller photo. The image limit is 20 megapixels.")
                gps = _photo_gps(original)
                with ImageOps.exif_transpose(original).convert("RGB") as oriented:
                    with Image.frombytes("RGB", oriented.size, oriented.tobytes()) as clean:
                        clean.save(output, format="JPEG", quality=90)
    except InvalidCheckinPhoto:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise InvalidCheckinPhoto("Take a new photo. This image could not be read.") from error
    return gps, output.getvalue()
