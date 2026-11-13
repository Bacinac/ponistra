"""One emoji, as Unicode recommends it be shown (UTS #51, RGI): a reaction to a message in mail
or in a conversation is exactly one."""

import icu

RGI = icu.UnicodeSet("[:RGI_Emoji:]")


def qualified(given) -> str:
    """The one emoji `given` is, fully qualified; empty unless it is exactly one."""
    if not isinstance(given, str) or not given:
        return ""
    for each in (given, given + "️"):
        if RGI.contains(each):
            return each
    return ""
