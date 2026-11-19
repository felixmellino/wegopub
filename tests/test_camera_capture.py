import base64
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

import camera_capture as camera
from core.checkin_photo import InvalidCheckinPhoto


def reading():
    image = BytesIO()
    exif = Image.Exif()
    exif[270] = 'Private camera metadata'
    Image.new('RGB', (20, 10)).save(image, 'JPEG', exif=exif)
    return {'capture_id': str(uuid4()), 'image': 'data:image/jpeg;base64,' + base64.b64encode(image.getvalue()).decode()}


def test_camera_bytes_are_validated_stripped_and_keep_capture_identity(monkeypatch):
    value = reading()
    monkeypatch.setattr(camera, '_camera_capture', lambda **kwargs: value)
    first, second = camera.camera_photo(key='one'), camera.camera_photo(key='one')
    assert first.file_id == second.file_id == value['capture_id']
    assert first.getvalue() == second.getvalue()
    with Image.open(first) as image:
        assert image.size == (20, 10) and not image.getexif()


def test_waiting_and_retake_return_no_photo(monkeypatch):
    monkeypatch.setattr(camera, '_camera_capture', lambda **kwargs: None)
    assert camera.camera_photo(key='new-photo') is None


def test_closing_camera_is_distinct_from_waiting(monkeypatch):
    monkeypatch.setattr(camera, '_camera_capture', lambda **kwargs: {'cancelled': True})
    with pytest.raises(camera.CameraCancelled):
        camera.camera_photo(key='cancel')


@pytest.mark.parametrize('value', [[], {}, {'capture_id':'bad', 'image':'data:image/jpeg;base64,AAAA'},
    {'capture_id':str(uuid4()), 'image':'data:image/png;base64,AAAA'},
    {'capture_id':str(uuid4()), 'image':'data:image/jpeg;base64,@@@'},
    {'capture_id':str(uuid4()), 'image':'data:image/jpeg;base64,AAAA'}])
def test_malformed_camera_value_is_rejected(monkeypatch, value):
    monkeypatch.setattr(camera, '_camera_capture', lambda **kwargs: value)
    with pytest.raises(InvalidCheckinPhoto):
        camera.camera_photo(key='bad')


def test_oversized_payload_is_rejected_before_decode(monkeypatch):
    value = reading()
    monkeypatch.setattr(camera, 'MAX_PHOTO_BYTES', 3)
    monkeypatch.setattr(camera, '_camera_capture', lambda **kwargs: value)
    with pytest.raises(InvalidCheckinPhoto, match='upload limit'):
        camera.camera_photo(key='large')
