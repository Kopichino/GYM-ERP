"""Private delivery for files that are nobody else's business.

Cloudinary's default delivery type is `upload`, which means public: the asset
is served to anyone who has the URL, with no authentication and no notion of
which gym it belongs to. That is right for a gallery photo the gym wants people
to see, and wrong for an expense receipt, which is a financial document
belonging to one branch.

Two mechanisms, and the difference matters:

* `type=authenticated` at upload time. The plain URL stops working outright --
  there is no public address for the asset any more. This is the part that
  closes the exposure, and it is unconditional.
* `sign_url=True` when building a URL. The signature is derived from the
  public id and the account secret, so a reader cannot forge one for an asset
  they were never given. This is what lets an authorised caller still see it.

A signed URL does not expire on its own. Cloudinary's time-limited URLs use a
separate token mechanism keyed on `CLOUDINARY_AUTH_TOKEN_KEY`, which is not
available on every plan -- so it is used when that key is configured and simply
not used when it is not. Without it, a signed URL that leaks stays valid, which
is a much smaller hole than the one it replaces but is not zero: treat a
receipt URL as something to keep, not something to paste into a group chat.

Everything Cloudinary is imported lazily. `cloudinary_storage` validates
credentials at import time and raises `ImproperlyConfigured` without them, so a
module-level import would make this file unimportable on a developer's machine
and in CI -- both of which run on the filesystem and have no Cloudinary account.
"""

import time

from django.conf import settings
from django.core.files.storage import default_storage

DEFAULT_URL_TTL_SECONDS = 10 * 60

_private_storage = None


def _build_storage_class():
    """Define the storage class against a configured Cloudinary.

    Built on first use rather than at import, for the reason in the module
    docstring: importing `cloudinary_storage.storage` without credentials
    raises, and this module has to be importable everywhere the models are.
    """
    import cloudinary
    from cloudinary.utils import cloudinary_url
    from cloudinary_storage.storage import MediaCloudinaryStorage

    class AuthenticatedCloudinaryStorage(MediaCloudinaryStorage):
        """Uploads privately and hands back signed URLs.

        `RESOURCE_TYPE` stays "image": Cloudinary treats PDFs as images, and
        `core.uploads` constrains receipts to images and PDFs, so one resource
        type covers everything this storage accepts.
        """

        DELIVERY_TYPE = "authenticated"

        def _upload(self, name, content):
            options = {
                "use_filename": True,
                "resource_type": self._get_resource_type(name),
                "tags": self.TAG,
                # The line that closes the hole. Without it Cloudinary stores
                # the asset as `upload`, which is world-readable.
                "type": self.DELIVERY_TYPE,
            }
            folder = name.rsplit("/", 1)[0] if "/" in name else ""
            if folder:
                options["folder"] = folder
            return cloudinary.uploader.upload(content, **options)

        def delete(self, name):
            # Must name the delivery type, or Cloudinary looks for a public
            # asset that does not exist and reports success having deleted
            # nothing -- leaving the receipt in place after a purge.
            response = cloudinary.uploader.destroy(
                name,
                invalidate=True,
                resource_type=self._get_resource_type(name),
                type=self.DELIVERY_TYPE,
            )
            return response["result"] == "ok"

        def url(self, name, ttl_seconds=DEFAULT_URL_TTL_SECONDS):
            name = self._prepend_prefix(name)
            options = {
                "type": self.DELIVERY_TYPE,
                "resource_type": self._get_resource_type(name),
                "sign_url": True,
                "secure": True,
            }
            token_key = getattr(settings, "CLOUDINARY_AUTH_TOKEN_KEY", "")
            if token_key:
                # Time-limited delivery, where the plan provides for it.
                options["auth_token"] = {
                    "key": token_key,
                    "duration": ttl_seconds,
                    "start_time": int(time.time()),
                }
            built, _ = cloudinary_url(name, **options)
            return built

    return AuthenticatedCloudinaryStorage


def private_media_storage():
    """Storage for files that must not be publicly addressable.

    A callable rather than an instance so the choice is made at runtime and
    migrations do not bake a backend into the schema -- local development runs
    on the filesystem, where privacy is a matter of the machine rather than of
    the URL.
    """
    global _private_storage

    if not getattr(settings, "CLOUDINARY_CLOUD_NAME", ""):
        return default_storage

    if _private_storage is None:
        _private_storage = _build_storage_class()()
    return _private_storage
