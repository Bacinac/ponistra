import pytest

from apps.core import sealed
from apps.mail.models import Account
from apps.users.models import User

from .mox import PASSWORD, own_folder


@pytest.fixture
def account():
    owner = User.objects.create_user("ivo@example.com", "Kamen-Most-Rijeka-71")
    return Account.objects.create(
        owner=owner,
        address="mox@localhost",
        username="mox@localhost",
        secret=sealed.seal("mail", PASSWORD),
        imap_host="mox",
        imap_port=1143,
        imap_security="none",
        smtp_host="mox",
        smtp_port=1587,
        smtp_security="none",
    )


@pytest.fixture
def folder():
    with own_folder() as name:
        yield name
