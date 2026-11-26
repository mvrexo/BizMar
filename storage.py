"""Local-only product image storage. No remote credentials or requests."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4
import warnings
from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent
IMAGE_DIR = ROOT / 'assets' / 'uploads' / 'products'
MAX_BYTES = 5 * 1024 * 1024


def validated_image_bytes(file):
    """Validate and normalize uploads for both preview and persistent storage."""
    data = file.getvalue()
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Image must be non-empty and no larger than 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in ('JPEG', 'PNG', 'WEBP'):
                    raise ValueError('Only JPG, PNG and WEBP images are allowed.')
                image.verify()
            with Image.open(BytesIO(data)) as image:
                if image.width * image.height > 20_000_000:
                    raise ValueError('Image must contain at most 20 million pixels.')
                output = BytesIO()
                image.convert('RGBA').save(output, format='PNG')
    except (OSError, UnidentifiedImageError, Image.DecompressionBombWarning, Image.DecompressionBombError) as error:
        raise ValueError('The uploaded file is not a valid image.') from error
    return output.getvalue()


def upload_product_image(file, product_id):
    from orders_store import current_owner
    current_owner()
    data = validated_image_bytes(file)
    directory = IMAGE_DIR.resolve()
    if not directory.is_relative_to((ROOT / 'assets').resolve()) or any(p.is_symlink() for p in (ROOT / 'assets', IMAGE_DIR.parent, IMAGE_DIR)):
        raise ValueError('Product images must stay in the local assets directory.')
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'product-{int(product_id)}-{uuid4().hex}.png'
    try:
        with path.open('xb') as target:
            target.write(data)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path.relative_to(ROOT).as_posix()
