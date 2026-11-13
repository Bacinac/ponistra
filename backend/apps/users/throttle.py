"""Guessing passwords, held three ways: one account from one address after a few failures, one
address across every account, and one account from every address it never signed in from. The
last spares the addresses the account knows, so nobody outside can lock its owner out."""

from axes.attempts import get_cool_off_threshold
from axes.handlers.database import AxesDatabaseHandler
from axes.helpers import get_client_username, get_failure_limit
from axes.models import AccessAttempt, AccessLog
from django.conf import settings
from django.db.models import Sum


class Handler(AxesDatabaseHandler):
    def get_failures(self, request, credentials: dict | None = None) -> int:
        pair = super().get_failures(request, credentials)
        username = get_client_username(request, credentials)
        address = request.axes_ip_address
        recent = AccessAttempt.objects.filter(attempt_time__gte=get_cool_off_threshold(request))

        def failures(**match) -> int:
            return recent.filter(**match).aggregate(total=Sum("failures_since_start"))["total"] or 0

        held = failures(ip_address=address) >= settings.SIGN_IN_ADDRESS_LIMIT or (
            failures(username=username) >= settings.SIGN_IN_ACCOUNT_LIMIT
            and not AccessLog.objects.filter(username=username, ip_address=address).exists()
        )
        return max(pair, get_failure_limit(request, credentials)) if held else pair
