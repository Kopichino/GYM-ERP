"""Every picture a person can upload goes through the same checks as the gallery.

The gallery and receipts were hardened in `core.uploads`: the bytes have to be
the format the extension claims, the size is capped, and the stored name is
generated. A profile photo, a gym logo and a badge picture were plain
ImageFields -- decoded by Pillow, but stored under whatever name the browser
sent, with no cap on the admin uploads below the whole-request limit, and no
check that the extension and the bytes agree.
"""

import re

from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import MemberProfile
from accounts.serializers import MemberProfileSerializer
from branding.serializers import BrandingSerializer
from gamification.models import Badge, Criterion
from gamification.serializers import BadgeSerializer

from .testing import OneGymTestCase, png_bytes

GENERATED = re.compile(r"^[0-9a-f]{32}\.(png|jpe?g|webp|gif)$")
HTML = b"<!doctype html><html><body><script>alert(document.cookie)</script></body></html>"
SIX_MB = 6 * 1024 * 1024


class ImageUploadTests(OneGymTestCase):
    def setUp(self):
        super().setUp()
        self.member = self.person("snapper")
        self.profile = MemberProfile.objects.get(user=self.member)
        self.tier = Badge._meta.get_field("tier").choices[0][0]
        self.criterion = next(value for value in Criterion.values if value != Criterion.LIFT)

    def forms(self, upload_factory):
        """(label, form, field) for each image upload, each given its own copy of the file."""
        return [
            ("profile photo", MemberProfileSerializer(
                self.profile, data={"photo": upload_factory()}, partial=True), "photo"),
            ("gym logo", BrandingSerializer(data={"name": "Gym", "logo": upload_factory()}), "logo"),
            ("badge picture", BadgeSerializer(data={
                "code": "first-visit", "name": "First visit", "tier": self.tier,
                "criterion": self.criterion, "threshold": 1, "image": upload_factory(),
            }), "image"),
        ]

    def test_a_real_image_is_accepted_and_stored_under_a_generated_name(self):
        for label, form, field in self.forms(lambda: SimpleUploadedFile(
                "My Holiday Pic.png", png_bytes(), content_type="image/png")):
            with self.subTest(upload=label):
                self.assertTrue(form.is_valid(), form.errors)
                stored = form.validated_data[field].name
                self.assertRegex(stored, GENERATED)
                self.assertNotIn("Holiday", stored)

    def test_a_web_page_labelled_as_an_image_is_refused(self):
        for label, form, field in self.forms(lambda: SimpleUploadedFile(
                "pic.png", HTML, content_type="image/png")):
            with self.subTest(upload=label):
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_bytes_that_disagree_with_the_extension_are_refused(self):
        for label, form, field in self.forms(lambda: SimpleUploadedFile(
                "pic.gif", png_bytes(), content_type="image/gif")):
            with self.subTest(upload=label):
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_a_real_image_under_a_web_page_name_is_refused(self):
        for label, form, field in self.forms(lambda: SimpleUploadedFile(
                "pic.html", png_bytes(), content_type="text/html")):
            with self.subTest(upload=label):
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_an_oversized_image_is_refused(self):
        for label, form, field in self.forms(lambda: SimpleUploadedFile(
                "big.png", png_bytes() + b"\0" * SIX_MB, content_type="image/png")):
            with self.subTest(upload=label):
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
