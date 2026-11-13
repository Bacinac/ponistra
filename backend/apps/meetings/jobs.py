from apps.core.api import Refused
from apps.jobs.kinds import Kind

from . import recordings


def asked(request, data: dict) -> dict:
    """Only a recording that ends hands this job over, never a request."""
    raise Refused(400, "unknown_job")


KINDS = {recordings.KIND: Kind(asked, recordings.saved, saves=False)}
