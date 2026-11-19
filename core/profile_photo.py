"""Safe profile pictures and the audience allowed to see them."""
from io import BytesIO
from warnings import catch_warnings, simplefilter

from PIL import Image, ImageOps

MAX_PROFILE_PHOTO_BYTES = 10 * 1024 * 1024
MAX_PROFILE_PHOTO_PIXELS = 20_000_000
PROFILE_PHOTO_SIZE = 512


def prepare_profile_photo(raw: bytes) -> bytes:
    """Orient, centre-crop and re-encode pixels, discarding all metadata."""
    if not raw or len(raw) > MAX_PROFILE_PHOTO_BYTES:
        raise ValueError("Choose a picture up to 10 MB.")
    try:
        with catch_warnings():
            simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw), formats=('JPEG', 'PNG', 'WEBP')) as image:
                if image.width * image.height > MAX_PROFILE_PHOTO_PIXELS:
                    raise ValueError("Choose a picture with at most 20 megapixels.")
                if getattr(image, 'is_animated', False):
                    raise ValueError("Choose a still picture rather than an animation.")
                oriented = ImageOps.exif_transpose(image)
                rgba = ImageOps.fit(oriented.convert('RGBA'), (PROFILE_PHOTO_SIZE, PROFILE_PHOTO_SIZE),
                                    method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
                # Transparent library pictures get a white background.
                clean = Image.new('RGB', rgba.size, 'white')
                clean.paste(rgba, mask=rgba.getchannel('A'))
                output = BytesIO()
                clean.save(output, format='JPEG', quality=90)
                return output.getvalue()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, SyntaxError) as exc:
        raise ValueError("This picture couldn't be read. Choose a JPEG, PNG or WebP image.") from exc


def can_view_profile_photo(viewer: str, owner: str, relationships: list[dict]) -> bool:
    if viewer == owner:
        return True
    return any({r['sender_id'], r['recipient_id']} == {viewer, owner}
               and r['status'] in ('accepted', 'pending') for r in relationships)


def initials(username: str) -> str:
    parts = username.strip().split()
    return (''.join(p[0] for p in parts[:2]) if len(parts) > 1 else username.strip()[:2]).upper() or '?'
