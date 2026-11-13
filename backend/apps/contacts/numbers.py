"""Phone numbers told apart however they are written: `091 234 5678`, `+385 91 234 5678` and
`00385912345678` are one number, kept written the one way, internationally."""

import re

import phonenumbers
from django.conf import settings


def _read(number: str) -> phonenumbers.PhoneNumber | None:
    try:
        parsed = phonenumbers.parse(number, settings.PHONE_REGION)
    except phonenumbers.NumberParseException:
        return None
    return parsed if phonenumbers.is_possible_number(parsed) else None


def key(number: str) -> str:
    """The number in E.164; where it cannot be read as one, its digits, a leading + kept."""
    if (parsed := _read(number)) is not None:
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    digits = re.sub(r"\D", "", number)
    return f"+{digits}" if number.strip().startswith("+") and digits else digits


def written(number: str) -> str:
    """The number as PONISTRA keeps it, `+385 91 234 5678`; where it cannot be read as one, such
    as a short service number, as it was given."""
    if (parsed := _read(number)) is not None:
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
    return number.strip()


def typed(word: str) -> str:
    """A number's beginning as the user types it, `091`, `00385` or `+385`, as the digits its
    E.164 begins with."""
    if word.startswith("+"):
        return word[1:]
    if word.startswith("00"):
        return word[2:]
    if word.startswith("0"):
        return f"{phonenumbers.country_code_for_region(settings.PHONE_REGION)}{word[1:]}"
    return word
