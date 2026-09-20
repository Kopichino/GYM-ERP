"""JWT authentication that honours revocation. See `accounts.revocation`."""

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .revocation import is_revoked


class RevocableJWTAuthentication(JWTAuthentication):
    """SimpleJWT's own checks, then: has this token been ended early?"""

    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        if is_revoked(token):
            raise InvalidToken("This session has ended. Sign in again.")
        return token
