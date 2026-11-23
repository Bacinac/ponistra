from django.conf import settings
from django.db import models


class Host(models.Model):
    """A location whose server runs Docker, reached as the location is, by SSH, but signed in to
    with a key of its own (D55): its `authorized_keys` line forces a command that lets through
    only the Engine API (`docker system dial-stdio`) and `docker compose` in a stack's folder.
    Docker there is root on the server, so only an administrator sets it up and uses it."""

    location = models.OneToOneField(
        "locations.Location",
        primary_key=True,
        on_delete=models.DB_CASCADE,
        related_name="docker",
    )
    secret = models.BinaryField()
    public_key = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.DB_SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"docker on {self.location_id}"
