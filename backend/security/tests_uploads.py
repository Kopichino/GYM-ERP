"""Uploaded files.

The browser's content type is whatever the client chose to send, and the file
name is whatever it chose to call the file, so neither decides anything here:

* the bytes have to be what the extension says -- an HTML page named `.png`
  and labelled `image/png` was accepted into the gallery, and a web page
  labelled `application/pdf` was accepted as a receipt;
* the stored name is generated, never the browser's;
* size is capped per kind of file, and the request as a whole is capped before
  anything reads it.
"""

import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import MemberProfile, Role
from accounts.serializers import MemberProfileSerializer
from branding.serializers import BrandingSerializer
from expenses.models import Expense, ExpenseCategory
from gallery.models import GalleryPost

from .testing import OneGymTestCase, png_bytes

TEMP_MEDIA = tempfile.mkdtemp(prefix="ironcore-uploads-")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class GalleryUploadTests(OneGymTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.person("snapper")
        self.client.force_authenticate(self.member)

    def upload(self, name, content, content_type, media_type="image"):
        return self.client.post(
            "/api/gallery/",
            {
                "media": SimpleUploadedFile(name, content, content_type=content_type),
                "media_type": media_type,
            },
            format="multipart",
        )

    def test_a_web_page_labelled_as_a_png_is_refused(self):
        resp = self.upload(
            "pic.png", b"<html><script>alert(document.cookie)</script></html>", "image/png"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(GalleryPost.objects.exists())

    def test_a_real_image_under_a_web_page_extension_is_refused(self):
        resp = self.upload("pic.html", png_bytes(), "image/png")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(GalleryPost.objects.exists())

    def test_a_file_that_is_not_a_video_is_refused_as_a_video(self):
        resp = self.upload("clip.mp4", b"MZ\x90\x00this is a program", "video/mp4", "video")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(GalleryPost.objects.exists())

    def test_the_stored_name_is_generated_not_taken_from_the_browser(self):
        resp = self.upload("../../evil name.png", png_bytes(), "image/png")
        self.assertEqual(resp.status_code, 201, resp.content)
        stored = GalleryPost.objects.get().media.name
        self.assertTrue(stored.startswith("gallery/"), stored)
        self.assertNotIn("..", stored)
        self.assertNotIn("evil", stored)
        self.assertTrue(stored.endswith(".png"), stored)

    def test_a_genuine_photo_is_accepted(self):
        self.assertEqual(self.upload("gym.png", png_bytes(), "image/png").status_code, 201)


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class ReceiptUploadTests(OneGymTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.person("owner", Role.ADMIN)
        self.category = ExpenseCategory.objects.create(name="Repairs")
        self.client.force_authenticate(self.admin)

    def record(self, name, content, content_type):
        return self.client.post(
            "/api/expenses/",
            {
                "category": self.category.pk,
                "amount": "120.00",
                "spent_on": timezone.localdate().isoformat(),
                "receipt": SimpleUploadedFile(name, content, content_type=content_type),
            },
            format="multipart",
        )

    def test_a_web_page_claiming_to_be_a_pdf_is_refused(self):
        resp = self.record("bill.html", b"<html><script>steal()</script></html>", "application/pdf")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Expense.objects.exists())

    def test_a_file_named_pdf_that_is_not_a_pdf_is_refused(self):
        resp = self.record("bill.pdf", b"MZ\x90\x00\x03\x00\x00\x00", "application/pdf")
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Expense.objects.exists())

    def test_a_real_pdf_receipt_is_accepted(self):
        resp = self.record("bill.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n", "application/pdf")
        self.assertEqual(resp.status_code, 201, resp.content)


class ImageFieldTests(OneGymTestCase):
    def test_an_oversized_profile_photo_is_refused(self):
        member = self.person("big")
        profile = MemberProfile.objects.get(user=member)
        # A valid PNG padded past the photo limit: Pillow reads it happily, so
        # only an explicit size check stops it.
        photo = SimpleUploadedFile(
            "me.png", png_bytes() + b"\0" * (6 * 1024 * 1024), content_type="image/png"
        )
        form = MemberProfileSerializer(profile, data={"photo": photo}, partial=True)
        self.assertFalse(form.is_valid())
        self.assertIn("photo", form.errors)

    def test_a_document_is_not_accepted_as_a_photo(self):
        member = self.person("doc")
        profile = MemberProfile.objects.get(user=member)
        photo = SimpleUploadedFile("me.png", b"%PDF-1.4 not an image", content_type="image/png")
        form = MemberProfileSerializer(profile, data={"photo": photo}, partial=True)
        self.assertFalse(form.is_valid())

    def test_a_vector_logo_is_refused(self):
        """SVG can carry script; the logo field only takes raster images."""
        logo = SimpleUploadedFile(
            "logo.svg",
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            content_type="image/svg+xml",
        )
        form = BrandingSerializer(data={"name": "Gym", "logo": logo})
        self.assertFalse(form.is_valid())
        self.assertIn("logo", form.errors)


class RequestSizeTests(APITestCase):
    def test_a_request_declaring_a_huge_body_is_refused_before_it_is_read(self):
        resp = self.client.generic(
            "POST",
            "/api/gallery/",
            data=b"x",
            content_type="multipart/form-data; boundary=abc",
            CONTENT_LENGTH=str(200 * 1024 * 1024),
        )
        self.assertEqual(resp.status_code, 413)


class ImportFileTests(OneGymTestCase):
    def setUp(self):
        super().setUp()
        self.admin = self.person("importer", Role.ADMIN)
        self.client.force_authenticate(self.admin)

    def preview(self, upload, **extra):
        return self.client.post(
            "/api/import/preview/", {"kind": "member", "file": upload, **extra}, format="multipart"
        )

    def test_a_file_pretending_to_be_a_spreadsheet_is_a_clean_400(self):
        resp = self.preview(
            SimpleUploadedFile("members.xlsx", b"definitely not a zip archive", content_type=XLSX)
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.data)

    def test_a_malformed_column_mapping_is_a_clean_400(self):
        rows = SimpleUploadedFile(
            "members.csv", b"First Name,Email\nAsha,asha@example.com\n", content_type="text/csv"
        )
        resp = self.preview(rows, mapping="{not json")
        self.assertEqual(resp.status_code, 400)

    def test_an_oversized_import_file_is_refused(self):
        big = b"First Name,Email\n" + b"Asha," + b"x" * (6 * 1024 * 1024) + b"@example.com\n"
        resp = self.preview(SimpleUploadedFile("members.csv", big, content_type="text/csv"))
        self.assertEqual(resp.status_code, 400)
