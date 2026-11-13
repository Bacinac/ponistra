import pytest

from apps.users.models import User


def _person(email: str, first: str, last: str) -> User:
    return User.objects.create_user(email, "Kamen-Most-Rijeka-71", first_name=first, last_name=last)


@pytest.fixture
def owner():
    return _person("ivo@example.com", "Ivo", "Bošković")


@pytest.fixture
def ana():
    return _person("ana@example.com", "Ana", "Kovač")
