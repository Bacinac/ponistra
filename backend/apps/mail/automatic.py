"""Telling what a program wrote from what a person did (RFC 3834, section 2)."""

import re
from email.message import Message as Parsed

from .mime import header

# The return addresses RFC 3834 names, and those that say no one reads them.
ROBOT = re.compile(
    r"owner-.*|.*-request|mailer-daemon|postmaster|bounces?([-+.].*)?"
    r"|do[-_.]?not[-_.]?reply.*|no[-_.]?reply.*",
    re.IGNORECASE,
)


def robot(address: str) -> bool:
    return ROBOT.fullmatch(address.partition("@")[0]) is not None


def by_program(message: Parsed, sender: str) -> bool:
    """Whether a program answered or reported rather than someone writing: an absence notice is
    no answer to what the user is waiting on."""
    submitted = header(message, "Auto-Submitted").partition(";")[0].strip().lower()
    return (
        submitted not in ("", "no")
        or bool(header(message, "X-Autoreply") or header(message, "X-Autorespond"))
        or header(message, "Return-Path").strip() == "<>"
        or robot(sender)
    )


def asks_no_answer(message: Parsed) -> bool:
    """Whether the message went to many or says it wants no automatic answer."""
    suppressed = header(message, "X-Auto-Response-Suppress").lower()
    return (
        any(name.lower().startswith("list-") for name in message.keys())
        or header(message, "Precedence").strip().lower() in ("bulk", "list", "junk", "auto_reply")
        or "oof" in suppressed
        or "all" in suppressed
    )
