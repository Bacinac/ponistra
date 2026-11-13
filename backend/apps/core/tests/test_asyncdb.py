import pytest
from django.db import connection, transaction

from apps.core.asyncdb import released


@pytest.mark.django_db(transaction=True)
def test_a_thread_gives_its_connection_back_before_it_waits():
    connection.ensure_connection()
    released()
    assert connection.connection is None


@pytest.mark.django_db(transaction=True)
def test_a_transaction_keeps_its_connection():
    with transaction.atomic():
        connection.ensure_connection()
        held = connection.connection
        released()
        assert connection.connection is held
