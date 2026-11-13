"""Values as a room keeps them, read back strictly: whatever its editors wrote may be anything."""

import math
from datetime import datetime


def finite(values: object, count: int | None = None) -> bool:
    """A list of numbers, `count` of them or pairs of at least one."""
    return (
        isinstance(values, list)
        and (len(values) == count if count else len(values) >= 2 and len(values) % 2 == 0)
        and all(
            isinstance(each, int | float) and not isinstance(each, bool) and math.isfinite(each)
            for each in values
        )
    )


def whole(value: object) -> int | None:
    """A whole number as Yjs gives it back, which is a float."""
    if isinstance(value, int | float) and not isinstance(value, bool) and float(value).is_integer():
        return int(value)
    return None


def moment(at: object) -> datetime | None:
    try:
        when = datetime.fromisoformat(at) if isinstance(at, str) else None
    except ValueError:
        return None
    return when if when is not None and when.tzinfo is not None else None
