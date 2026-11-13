import base64

import pytest

from apps.calendar import taking
from apps.core import sealed
from apps.mail.models import Account
from apps.mail.tests import eas
from apps.users.app_passwords import digest, made
from apps.users.models import AppPassword, User


@pytest.fixture
def owner():
    return User.objects.create_user(
        "ivo@example.com", "Kamen-Most-Rijeka-71", first_name="Ivo", last_name="Bošković"
    )


@pytest.fixture
def own(owner):
    return taking.own(owner.pk, "Moj")


@pytest.fixture
def signed_in(client, owner):
    client.force_login(owner)
    return client


@pytest.fixture
def phone(client, owner):
    secret = made()
    AppPassword.objects.create(user=owner, name="iPhone", digest=digest(secret))
    token = base64.b64encode(f"ivo@example.com:{secret}".encode()).decode()
    client.defaults["HTTP_AUTHORIZATION"] = f"Basic {token}"
    return client


@pytest.fixture
def box(settings):
    settings.MAIL_PLAIN_HOSTS = {"127.0.0.1"}
    mailbox = eas.Mailbox()
    server = eas.serve(mailbox)
    mailbox.host = f"127.0.0.1:{server.server_address[1]}"
    yield mailbox
    server.shutdown()
    server.server_close()


@pytest.fixture
def account(box, owner):
    return Account.objects.create(
        owner=owner,
        address=eas.USER,
        username=eas.USER,
        secret=sealed.seal("mail", eas.PASSWORD),
        protocol=Account.Protocol.ACTIVESYNC,
        activesync_host=box.host,
        device="5c1d" * 8,
    )
