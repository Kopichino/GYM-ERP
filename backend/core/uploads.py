"""Shared limits for uploaded files.

Django checks more than it looks like it does: an `ImageField` is verified
through Pillow before it is accepted, so a `.exe` renamed to `.png` is refused
on the profile-photo and logo paths without anything extra here. A `FileField`
gets no such treatment -- whatever arrives is written -- which is why the
expense receipt path needed this and the photo paths did not.

Neither Django nor this module can trust the browser-supplied content type; it
is whatever the client said. The extension check is therefore a convenience for
the person uploading, and the size cap is the part that actually protects the
service. Anything stronger means sniffing magic bytes, which is worth doing if
receipts ever become member-uploadable rather than admin-only.
"""

from rest_framework import serializers

# Cloudinary's free tier is the binding constraint, not the disk.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# What a receipt plausibly is: a photo of a bill, or a supplier's PDF.
RECEIPT_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "application/pdf",
}
RECEIPT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".pdf"}


def validate_upload(uploaded, *, allowed_types, allowed_extensions, max_bytes=MAX_UPLOAD_BYTES):
    """Refuse an upload that is too big or obviously the wrong kind of file.

    Returns the file so it can be used as a serializer field validator.
    """
    if not uploaded:
        return uploaded

    size = getattr(uploaded, "size", 0) or 0
    if size > max_bytes:
        raise serializers.ValidationError(
            f"That file is {size // (1024 * 1024)}MB; the limit is {max_bytes // (1024 * 1024)}MB."
        )

    name = (getattr(uploaded, "name", "") or "").lower()
    extension = name[name.rfind(".") :] if "." in name else ""
    content_type = (getattr(uploaded, "content_type", "") or "").lower()

    # Either signal being right is enough: some browsers send
    # application/octet-stream for a perfectly ordinary PDF, and refusing that
    # would block a genuine receipt for no security gain.
    if extension not in allowed_extensions and content_type not in allowed_types:
        raise serializers.ValidationError(
            f"{extension or content_type or 'That file'} isn't an accepted receipt format "
            f"({', '.join(sorted(allowed_extensions))})."
        )
    return uploaded


def validate_receipt(uploaded):
    return validate_upload(
        uploaded,
        allowed_types=RECEIPT_CONTENT_TYPES,
        allowed_extensions=RECEIPT_EXTENSIONS,
    )
