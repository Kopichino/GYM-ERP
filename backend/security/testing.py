"""Fixtures shared by the security suites.

Most of these tests sign in with a real bearer token rather than DRF's
`force_authenticate`. Forcing a user skips the authentication classes entirely,
and the checks that a token is still live and that its holder has standing at
the gym in the URL both live there -- a suite built on forced users would keep
passing with those checks deleted.
"""

import io
import time

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import MemberProfile, Role
from core.testing import TenantAPIMixin
from tenancy.models import Membership, Organisation, Tenant

User = get_user_model()

PASSWORD = "correct-horse-battery-42"


def make_gym(slug):
    organisation = Organisation.objects.create(name=slug.title(), slug=slug)
    return Tenant.objects.create(
        organisation=organisation, name=slug.title(), slug=f"{slug}-main"
    )


def make_person(username, *, gym=None, role=Role.MEMBER, **fields):
    """An account, with a Membership at `gym` when one is given."""
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password=PASSWORD,
        role=role,
        **fields,
    )
    MemberProfile.objects.get_or_create(user=user)
    if gym is not None:
        Membership.objects.create(user=user, tenant=gym, role=role)
    return user


def bearer(user, issued_seconds_ago=0):
    """An access token as the browser holds one.

    `issued_seconds_ago` backdates it, for tests about tokens issued before
    something revoked them -- revocation works to the second, so a token minted
    in the same second as the revocation is deliberately still honoured.
    """
    token = AccessToken.for_user(user)
    if issued_seconds_ago:
        token["iat"] = int(time.time()) - issued_seconds_ago
    return str(token)


def png_bytes(size=(4, 4)):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, "red").save(buffer, "PNG")
    return buffer.getvalue()


class TwoGymsTestCase(APITestCase):
    """Two unrelated gyms. Nobody is enrolled anywhere unless a test says so."""

    def setUp(self):
        super().setUp()
        # Throttle and back-off state lives in the cache, which outlives a test.
        cache.clear()
        self.gym_a = make_gym("gym-a")
        self.gym_b = make_gym("gym-b")

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def at(self, gym):
        return f"/api/t/{gym.slug}"

    def sign_in(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {bearer(user)}")


class OneGymTestCase(TenantAPIMixin, APITestCase):
    """One gym, with the client's /api/ paths pointed at it."""

    def setUp(self):
        super().setUp()
        cache.clear()

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def person(self, username, role=Role.MEMBER, **fields):
        user = make_person(username, role=role, **fields)
        self.member_for(user, role)
        return user
