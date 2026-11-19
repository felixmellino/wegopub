"""Profile image pixels, boundaries and audience rules."""
from io import BytesIO
from unittest.mock import patch
from PIL import Image
import pytest
from core.profile_photo import (prepare_profile_photo, can_view_profile_photo, initials,
                                MAX_PROFILE_PHOTO_BYTES, MAX_PROFILE_PHOTO_PIXELS)


def picture(format='PNG', size=(800, 400)):
    im = Image.new('RGB', size, 'red')
    # Different coloured edges prove the crop uses the centre.
    im.paste('blue', (0, 0, 200, 400))
    im.paste('green', (600, 0, 800, 400))
    out = BytesIO()
    exif = Image.Exif()
    exif[270] = 'Private metadata'
    im.save(out, format=format, exif=exif)
    return out.getvalue()


@pytest.mark.parametrize('format', ['PNG', 'JPEG', 'WEBP'])
def test_square_centre_crop_and_metadata_removed(format):
    result = prepare_profile_photo(picture(format))
    with Image.open(BytesIO(result)) as im:
        assert im.size == (512, 512)
        assert im.format == 'JPEG'
        assert not im.getexif()
        red, green, blue = im.getpixel((256, 256))
        assert red > 200 and green < 30 and blue < 30


@pytest.mark.parametrize('raw', [b'', b'not an image', b'x' * (MAX_PROFILE_PHOTO_BYTES + 1)],
                         ids=['empty', 'not-an-image', 'too-large'])
def test_invalid_image_rejected(raw):
    with pytest.raises(ValueError):
        prepare_profile_photo(raw)


def test_dimension_limit_before_pixel_decode():
    with patch('core.profile_photo.MAX_PROFILE_PHOTO_PIXELS', 319999):
        with pytest.raises(ValueError, match='20 megapixels'):
            prepare_profile_photo(picture())
    with patch('core.profile_photo.MAX_PROFILE_PHOTO_PIXELS', 320000):
        assert prepare_profile_photo(picture())


def test_rotation_and_transparency():
    im = Image.new('RGBA', (20, 40), (255, 0, 0, 0))
    out = BytesIO()
    im.save(out, format='PNG')
    with Image.open(BytesIO(prepare_profile_photo(out.getvalue()))) as saved:
        assert saved.getpixel((256, 256)) == (255, 255, 255)
    exif = Image.Exif()
    exif[274] = 6
    im = Image.new('RGB', (200, 200), 'red')
    im.paste('blue', (0, 0, 100, 200))
    out = BytesIO()
    im.save(out, format='JPEG', exif=exif)
    with Image.open(BytesIO(prepare_profile_photo(out.getvalue()))) as saved:
        assert saved.getpixel((256, 30))[2] > 200  # left side rotated to the top
        assert not saved.getexif()


@pytest.mark.parametrize('status,allowed', [('pending', True), ('accepted', True), ('declined', False), ('removed', False)])
def test_friend_picture_audience(status, allowed):
    relationship = {'sender_id': 'a', 'recipient_id': 'b', 'status': status}
    assert can_view_profile_photo('a', 'b', [relationship]) is allowed
    assert can_view_profile_photo('b', 'a', [relationship]) is allowed
    assert not can_view_profile_photo('outsider', 'b', [relationship])


def test_owner_stranger_cancelled_request_and_initials():
    assert can_view_profile_photo('a', 'a', [])
    assert not can_view_profile_photo('a', 'b', [])
    assert initials('Mia Silva') == 'MS'
    assert initials('mia') == 'MI'
    assert initials(' ') == '?'
