from django.conf import settings
from django.db import models


class CheckInOut(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="check_ins"
    )
    check_in_time = models.DateTimeField(auto_now_add=True)
    check_out_time = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-check_in_time"]
        constraints = [
            # At most one open (not-yet-checked-out) record per user.
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(check_out_time__isnull=True),
                name="one_open_checkin_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user} @ {self.check_in_time:%Y-%m-%d %H:%M}"
