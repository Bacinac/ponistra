"""A password checked by the LDAP directory that keeps its person (U1), after the installation's
own passwords have refused it."""

from logging import getLogger

from django.contrib.auth.backends import BaseBackend

from apps.users.models import User

from . import directory
from .models import Identity, Provider
from .people import Refusal

log = getLogger(__name__)


class Directory(BaseBackend):
    def authenticate(self, request, email=None, password=None, **kwargs):
        if not email or not password:
            return None
        identity = (
            Identity.objects.select_related("user", "provider")
            .filter(
                user__email=str(email).strip().lower(),
                user__is_active=True,
                provider__kind=Provider.Kind.LDAP,
                provider__enabled=True,
                provider__settings__sign_in=True,
            )
            .first()
        )
        name = identity and identity.detail.get("dn")
        if not name:
            return None
        try:
            if directory.checked(identity.provider, name, password):
                return identity.user
        except Refusal as refusal:
            log.warning("identity: %s could not check a password: %s", identity.provider, refusal)
        return None

    def get_user(self, user_id):
        return User._default_manager.filter(pk=user_id, is_active=True).first()
