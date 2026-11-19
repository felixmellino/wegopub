"""Streamlit bridge for an automatically opened camera; no gallery uploads."""
import base64
import binascii
from io import BytesIO
from pathlib import Path
from uuid import UUID

from streamlit.components.v1 import declare_component

from core.checkin_photo import InvalidCheckinPhoto, MAX_PHOTO_BYTES, prepare_checkin_photo

_camera_capture = declare_component('drink_camera', path=str(Path(__file__).parent / 'components' / 'drink_camera'))


class CameraCancelled(Exception):
    """The player closed the camera without taking a photo."""


def camera_photo(*, key: str) -> BytesIO | None:
    """Return one validated camera JPEG, retaining its identity across reruns."""
    value = _camera_capture(key=key, default=None)
    if value is None:
        return None
    if value == {'cancelled': True}:
        raise CameraCancelled
    try:
        if not isinstance(value, dict):
            raise ValueError
        capture_id = str(UUID(value['capture_id']))
        encoded = value['image']
        prefix = 'data:image/jpeg;base64,'
        if not isinstance(encoded, str) or not encoded.startswith(prefix):
            raise ValueError
        payload = encoded[len(prefix):]
        if len(payload) > 4 * ((MAX_PHOTO_BYTES + 2) // 3):
            raise InvalidCheckinPhoto('The camera photo exceeds the upload limit. Take another photo.')
        raw = base64.b64decode(payload, validate=True)
        _, cleaned = prepare_checkin_photo(raw)
    except (KeyError, TypeError, ValueError, binascii.Error) as exc:
        if isinstance(exc, InvalidCheckinPhoto):
            raise
        raise InvalidCheckinPhoto('The camera photo could not be read. Retake it and try again.') from None
    photo = BytesIO(cleaned)
    photo.file_id = capture_id
    return photo
