"""Receipts upload privately and are served through signed URLs.

The exposure this closes: Cloudinary's default delivery type is `upload`, so
every receipt sat at a public address with no authentication and no tenant in
the path. Financial documents belonging to paying gyms, readable by anyone
holding the link.

These tests drive the storage class directly with Cloudinary's uploader mocked.
That is the right seam -- what matters is the options the upload is asked to
make and the shape of the URL handed back, and neither needs a real account or
a network round trip to pin.
"""

import os
from unittest.mock import patch

# Set before anything imports `cloudinary_storage`: that package validates
# credentials at import time and raises without them. Its env-var branch is the
# one route that does not also require overriding CLOUDINARY_STORAGE, which is
# on its `setting_changed` watch list and forces a module reload that breaks on
# teardown. These are not real credentials and reach no network -- every upload
# below is mocked.
# `setdefault` is not enough: .env sets CLOUDINARY_CLOUD_NAME to an empty
# string, so the key exists and setdefault leaves the falsy value in place.
for _key, _value in (
    ("CLOUDINARY_CLOUD_NAME", "testcloud"),
    ("CLOUDINARY_API_KEY", "111111111111111"),
    ("CLOUDINARY_API_SECRET", "test-secret-not-real"),
):
    if not os.environ.get(_key):
        os.environ[_key] = _value

import cloudinary  # noqa: E402
from django.core.files.base import ContentFile  # noqa: E402
from django.core.files.storage import FileSystemStorage  # noqa: E402
from django.test import TestCase, override_settings  # noqa: E402

from core.storage import private_media_storage  # noqa: E402

cloudinary.config(
    cloud_name="testcloud", api_key="111111111111111", api_secret="test-secret-not-real"
)

# Only the plain string our own code reads. Deliberately not CLOUDINARY_STORAGE.
CLOUD = {"CLOUDINARY_CLOUD_NAME": "testcloud"}


def _reset_cache():
    """The storage instance is memoised, so a settings override in one test
    would otherwise be answered from the instance another test built."""
    import core.storage

    core.storage._private_storage = None


class StorageSelectionTests(TestCase):
    def tearDown(self):
        _reset_cache()
        super().tearDown()

    def test_without_cloudinary_it_falls_back_to_the_filesystem(self):
        # Local development and CI both run here. The module has to be usable
        # with no Cloudinary account at all.
        with override_settings(CLOUDINARY_CLOUD_NAME=""):
            _reset_cache()
            self.assertIsInstance(private_media_storage(), FileSystemStorage)

    @override_settings(**CLOUD)
    def test_with_cloudinary_it_uses_the_authenticated_backend(self):
        _reset_cache()
        storage = private_media_storage()
        self.assertEqual(storage.DELIVERY_TYPE, "authenticated")

    @override_settings(**CLOUD)
    def test_the_instance_is_reused(self):
        _reset_cache()
        self.assertIs(private_media_storage(), private_media_storage())


@override_settings(**CLOUD)
class AuthenticatedUploadTests(TestCase):
    def setUp(self):
        _reset_cache()
        self.storage = private_media_storage()

    def tearDown(self):
        _reset_cache()
        super().tearDown()

    def test_the_upload_asks_for_private_delivery(self):
        # The single line that closes the exposure. Without `type`, Cloudinary
        # stores the asset as `upload`, which is world-readable.
        with patch("cloudinary.uploader.upload", return_value={"public_id": "receipts/x"}) as up:
            self.storage._save("receipts/bill.pdf", ContentFile(b"%PDF-1.4", name="bill.pdf"))

        self.assertEqual(up.call_args.kwargs["type"], "authenticated")

    def test_the_upload_keeps_the_receipts_folder(self):
        with patch("cloudinary.uploader.upload", return_value={"public_id": "receipts/x"}) as up:
            self.storage._save("receipts/bill.pdf", ContentFile(b"%PDF-1.4", name="bill.pdf"))

        self.assertEqual(up.call_args.kwargs["folder"], "media/receipts")

    def test_deleting_names_the_delivery_type(self):
        # Without it Cloudinary looks for a public asset that does not exist,
        # reports success, and leaves the receipt exactly where it was.
        with patch("cloudinary.uploader.destroy", return_value={"result": "ok"}) as destroy:
            self.storage.delete("receipts/bill.pdf")

        self.assertEqual(destroy.call_args.kwargs["type"], "authenticated")


@override_settings(**CLOUD)
class SignedUrlTests(TestCase):
    def setUp(self):
        _reset_cache()
        self.storage = private_media_storage()

    def tearDown(self):
        _reset_cache()
        super().tearDown()

    def test_the_url_is_not_the_plain_public_form(self):
        url = self.storage.url("receipts/bill.pdf")

        # The old address -- /image/upload/<id> -- must not be what we hand out.
        self.assertNotIn("/image/upload/", url)
        self.assertIn("/authenticated/", url)

    def test_the_url_carries_a_signature(self):
        # `s--<sig>--` is Cloudinary's signed-URL marker. Without it any reader
        # could construct the address of any receipt from its public id.
        url = self.storage.url("receipts/bill.pdf")
        self.assertRegex(url, r"/s--[A-Za-z0-9_-]+--/")

    def test_the_url_is_https(self):
        self.assertTrue(self.storage.url("receipts/bill.pdf").startswith("https://"))

    def test_two_different_receipts_get_different_signatures(self):
        one = self.storage.url("receipts/a.pdf")
        two = self.storage.url("receipts/b.pdf")
        self.assertNotEqual(one, two)

    @override_settings(CLOUDINARY_AUTH_TOKEN_KEY="")
    def test_without_a_token_key_the_url_is_still_signed(self):
        # Time-limited delivery is a paid feature. Its absence must not silently
        # drop the signature and leave us back where we started.
        url = self.storage.url("receipts/bill.pdf")
        self.assertRegex(url, r"/s--[A-Za-z0-9_-]+--/")
        self.assertNotIn("__cld_token__", url)

    @override_settings(CLOUDINARY_AUTH_TOKEN_KEY="6b6e5a3f")
    def test_with_a_token_key_the_url_expires(self):
        url = self.storage.url("receipts/bill.pdf", ttl_seconds=300)
        self.assertIn("__cld_token__", url)


class PrivatiseReceiptsCommandTests(TestCase):
    """Moving receipts already uploaded.

    Without this, pointing the field at a private backend closes the exposure
    for new uploads and leaves every existing receipt public -- the worse half
    of the problem, and the half nobody notices because the code looks fixed.
    """

    def setUp(self):
        from decimal import Decimal

        from accounts.models import Role
        from django.contrib.auth import get_user_model
        from expenses.models import Expense, ExpenseCategory
        from tenancy import context

        from core.testing import founding_tenant

        _, self.tenant = founding_tenant("receiptgym")
        self._token = context.set(self.tenant)

        User = get_user_model()
        User.objects.create_user(
            username="rcpt_admin", email="r@example.com", password="pass12345", role=Role.ADMIN
        )
        category = ExpenseCategory.objects.create(name="Utilities")
        self.expense = Expense.objects.create(
            category=category, amount=Decimal("100"), receipt="media/receipts/bill.pdf"
        )

    def tearDown(self):
        from tenancy import context

        token = getattr(self, "_token", None)
        if token is not None:
            context.reset(token)
        _reset_cache()
        super().tearDown()

    def _run(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out, err = StringIO(), StringIO()
        call_command("privatise_receipts", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    @override_settings(CLOUDINARY_CLOUD_NAME="")
    def test_it_refuses_when_cloudinary_is_not_configured(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self._run()

    @override_settings(**CLOUD)
    def test_a_dry_run_changes_nothing(self):
        with patch("cloudinary.uploader.rename") as rename:
            out, _ = self._run()

        rename.assert_not_called()
        self.assertIn("would move", out)
        self.assertIn("Dry run", out)

    @override_settings(**CLOUD)
    def test_apply_moves_the_asset_to_authenticated(self):
        with patch("cloudinary.uploader.rename") as rename:
            out, _ = self._run("--apply")

        self.assertEqual(rename.call_count, 1)
        kwargs = rename.call_args.kwargs
        self.assertEqual(kwargs["type"], "upload")
        self.assertEqual(kwargs["to_type"], "authenticated")
        self.assertIn("Moved 1", out)

    @override_settings(**CLOUD)
    def test_the_public_id_is_unchanged_so_the_database_needs_no_rewrite(self):
        with patch("cloudinary.uploader.rename") as rename:
            self._run("--apply")

        args = rename.call_args.args
        self.assertEqual(args[0], args[1])
        self.expense.refresh_from_db()
        self.assertEqual(self.expense.receipt.name, "media/receipts/bill.pdf")

    @override_settings(**CLOUD)
    def test_a_second_run_is_harmless(self):
        # Cloudinary reports "not found" for an asset already moved, which is a
        # re-run rather than a failure.
        with patch("cloudinary.uploader.rename", side_effect=Exception("Resource not found")):
            out, _ = self._run("--apply")

        self.assertIn("already private 1", out)
        self.assertIn("Moved 0", out)

    @override_settings(**CLOUD)
    def test_a_real_failure_is_reported_loudly(self):
        from django.core.management.base import CommandError

        with patch("cloudinary.uploader.rename", side_effect=Exception("rate limited")):
            with self.assertRaises(CommandError):
                self._run("--apply")


@override_settings(**CLOUD)
class PrivatiseReceiptsLimitTests(TestCase):
    """`--limit` exists so the first contact with the live Cloudinary API is a
    handful of receipts rather than the whole book.

    Every other test in this file mocks the uploader, so the first `--apply`
    against production is the first time this code meets the real API. A scoped
    run is the only cheap way to find that out safely.
    """

    def setUp(self):
        from decimal import Decimal

        from expenses.models import Expense, ExpenseCategory
        from tenancy import context

        from core.testing import founding_tenant

        _, self.tenant = founding_tenant("limitgym")
        self._token = context.set(self.tenant)

        category = ExpenseCategory.objects.create(name="Utilities")
        self.expenses = [
            Expense.objects.create(
                category=category,
                amount=Decimal("100"),
                receipt=f"media/receipts/bill{n}.pdf",
            )
            for n in range(5)
        ]

    def tearDown(self):
        from tenancy import context

        token = getattr(self, "_token", None)
        if token is not None:
            context.reset(token)
        _reset_cache()
        super().tearDown()

    def _run(self, *args):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("privatise_receipts", *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_a_limit_caps_how_many_are_moved(self):
        with patch("cloudinary.uploader.rename") as rename:
            out = self._run("--apply", "--limit", "2")

        self.assertEqual(rename.call_count, 2)
        self.assertIn("Moved 2", out)

    def test_it_says_how_many_of_how_many(self):
        # So a dry run can be checked against the real receipt volume before
        # anything is committed.
        out = self._run("--limit", "2")
        self.assertIn("2 oldest of 5", out)

    def test_the_limit_takes_the_oldest_first(self):
        with patch("cloudinary.uploader.rename") as rename:
            self._run("--apply", "--limit", "2")

        moved = [call.args[0] for call in rename.call_args_list]
        self.assertEqual(moved, ["media/receipts/bill0.pdf", "media/receipts/bill1.pdf"])

    def test_a_larger_limit_later_picks_up_the_rest(self):
        # The first two report as already private on the second pass, so
        # widening the limit progresses rather than redoing work.
        def rename(public_id, _to, **kwargs):
            if public_id in {"media/receipts/bill0.pdf", "media/receipts/bill1.pdf"}:
                raise Exception("Resource not found")
            return {"public_id": public_id}

        with patch("cloudinary.uploader.rename", side_effect=rename):
            out = self._run("--apply", "--limit", "4")

        self.assertIn("Moved 2", out)
        self.assertIn("already private 2", out)

    def test_no_limit_takes_everything(self):
        with patch("cloudinary.uploader.rename") as rename:
            self._run("--apply")
        self.assertEqual(rename.call_count, 5)

    def test_a_nonsense_limit_is_refused(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self._run("--limit", "0")
