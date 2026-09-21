"""What an uploaded file is allowed to be.

Nothing the browser says about a file is trusted. Its content type is whatever
the client chose to send and its name is whatever it chose to call it -- an
HTML page named `pic.png` and labelled `image/png` is three claims, none of them
checked. So:

* the **extension** has to be one this kind of upload accepts;
* the **bytes** have to be that format, read from the file's own signature;
* the **stored name** is generated here, so a name like `../../x.html` never
  reaches storage and no uploaded file keeps a name somebody chose;
* the **size** is capped per kind of file, and the request as a whole is capped
  before anything reads it (`core.middleware.RequestSizeLimitMiddleware`).
"""

import os
import uuid

from rest_framework import serializers

# Cloudinary's free tier is the binding constraint, not the disk.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_GALLERY_BYTES = 20 * 1024 * 1024

# Kept for reference by callers; the content type is never used to decide.
RECEIPT_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "application/pdf",
}
RECEIPT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf"}
GALLERY_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".gif"},
    "video": {".mp4", ".m4v", ".mov", ".webm"},
}

#: The formats each extension may really contain.
EXTENSION_FORMATS = {
    ".png": {"png"},
    ".jpg": {"jpeg"},
    ".jpeg": {"jpeg"},
    ".gif": {"gif"},
    ".webp": {"webp"},
    ".heic": {"heic"},
    ".pdf": {"pdf"},
    ".mp4": {"mp4"},
    ".m4v": {"mp4"},
    ".mov": {"mov", "mp4"},
    ".webm": {"webm"},
}
IMAGE_FORMATS = {"png", "jpeg", "gif", "webp"}


def sniff(uploaded):
    """The format a file's own leading bytes declare, or None."""
    try:
        uploaded.seek(0)
        head = uploaded.read(16)
    finally:
        try:
            uploaded.seek(0)
        except Exception:  # noqa: BLE001 -- a stream that cannot rewind is read by nobody else
            pass
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"heic", b"heix", b"mif1", b"msf1"):
            return "heic"
        if brand == b"qt  ":
            return "mov"
        return "mp4"
    return None


def _extension(uploaded):
    name = (getattr(uploaded, "name", "") or "").lower()
    return os.path.splitext(os.path.basename(name))[1]


def validate_upload(uploaded, *, allowed_extensions, max_bytes=MAX_UPLOAD_BYTES, allowed_types=None):
    """Refuse a file that is too big, has the wrong extension, or whose bytes are
    not what its extension says. Renames what it accepts. `allowed_types` is
    accepted for older callers and deliberately ignored.
    """
    if not uploaded:
        return uploaded

    size = getattr(uploaded, "size", 0) or 0
    if size > max_bytes:
        raise serializers.ValidationError(
            f"That file is {size // (1024 * 1024)}MB; the limit is {max_bytes // (1024 * 1024)}MB."
        )

    extension = _extension(uploaded)
    if extension not in allowed_extensions:
        raise serializers.ValidationError(
            f"{extension or 'That file'} isn't an accepted format ({', '.join(sorted(allowed_extensions))})."
        )

    if sniff(uploaded) not in EXTENSION_FORMATS.get(extension, set()):
        raise serializers.ValidationError(
            f"That file's contents aren't a real {extension} file."
        )

    if sniff(uploaded) in IMAGE_FORMATS:
        from PIL import Image

        try:
            uploaded.seek(0)
            Image.open(uploaded).verify()
        except Exception:  # noqa: BLE001 -- anything Pillow cannot read is not an image
            raise serializers.ValidationError("That image could not be read.") from None
        finally:
            uploaded.seek(0)

    uploaded.name = f"{uuid.uuid4().hex}{extension}"
    return uploaded


def validate_receipt(uploaded):
    return validate_upload(uploaded, allowed_extensions=RECEIPT_EXTENSIONS)


def validate_gallery_media(uploaded, media_type):
    return validate_upload(
        uploaded,
        allowed_extensions=GALLERY_EXTENSIONS.get(media_type, set()),
        max_bytes=MAX_GALLERY_BYTES,
    )


def validate_image_upload(uploaded, max_bytes=MAX_PHOTO_BYTES):
    """A picture somebody picked: a profile photo, a gym logo, a badge.

    The same checks as the gallery -- real image bytes behind an allowed
    extension, a size cap and a generated stored name -- so none of the smaller
    image fields is a way around them.
    """
    return validate_upload(uploaded, allowed_extensions=GALLERY_EXTENSIONS["image"], max_bytes=max_bytes)


def validate_photo_size(photo):
    """Pillow reads a padded image happily, so only a size check stops one."""
    if photo and (getattr(photo, "size", 0) or 0) > MAX_PHOTO_BYTES:
        raise serializers.ValidationError(
            f"That photo is larger than {MAX_PHOTO_BYTES // (1024 * 1024)}MB."
        )
    return photo
