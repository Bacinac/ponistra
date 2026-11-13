import math
import re
from decimal import ROUND_HALF_UP, Decimal, localcontext

from .. import formats, numformat, sql
from ..criteria import wildcard
from ..values import NA, VALUE, Blank, Error, number, text
from . import form, sql_form

LONGEST = 32_767
EXACT = 400


def _long(result: str) -> str | Error:
    return VALUE if len(result) > LONGEST else result


@form("CONCATENATE")
def concatenate(context, *texts):
    return _long("".join(texts))


@form("CONCAT")
def concat(context, texts):
    return _long("".join(texts))


@form("TEXTJOIN")
def textjoin(context, delimiter, ignore_empty, texts):
    return _long(delimiter.join(each for each in texts if each or not ignore_empty))


@form("LEFT")
def left(context, value, count=1.0):
    if count < 0:
        return VALUE
    return value[: math.trunc(count)]


@form("RIGHT")
def right(context, value, count=1.0):
    if count < 0:
        return VALUE
    count = math.trunc(count)
    return value[-count:] if count else ""


@form("MID")
def mid(context, value, start, count):
    if start < 1 or count < 0:
        return VALUE
    start = math.trunc(start) - 1
    return value[start : start + math.trunc(count)]


@form("LEN")
def len_(context, value):
    return len(value)


def _found(find, within, start, pattern) -> int | Error:
    start = math.trunc(start)
    if start < 1 or start > max(len(within), 1):
        return VALUE
    if not find:
        return start
    found = pattern.search(within, start - 1)
    return VALUE if found is None else found.start() + 1


@form("FIND")
def find(context, find_text, within, start=1.0):
    return _found(find_text, within, start, re.compile(re.escape(find_text)))


@form("SEARCH")
def search(context, find_text, within, start=1.0):
    return _found(find_text, within, start, wildcard(find_text))


@form("SUBSTITUTE")
def substitute(context, value, old, new, instance=None):
    if instance is not None:
        instance = math.trunc(instance)
        if instance < 1:
            return VALUE
    if not old:
        return value
    if instance is None:
        return _long(value.replace(old, new))
    at = -1
    for _ in range(instance):
        at = value.find(old, at + 1 if at < 0 else at + len(old))
        if at < 0:
            return value
    return _long(value[:at] + new + value[at + len(old) :])


@form("REPLACE")
def replace(context, value, start, count, new):
    if start < 1 or count < 0:
        return VALUE
    start = math.trunc(start) - 1
    return _long(value[:start] + new + value[start + math.trunc(count) :])


@form("TRIM")
def trim(context, value):
    return " ".join(part for part in value.split(" ") if part)


@form("UPPER")
def upper(context, value):
    return value.upper()


@form("LOWER")
def lower(context, value):
    return value.lower()


@form("PROPER")
def proper(context, value):
    out = []
    after_letter = False
    for each in value:
        out.append(each.lower() if after_letter else each.upper())
        after_letter = each.isalpha()
    return "".join(out)


@form("TEXT")
def text_(context, value, code):
    match value:
        case bool():
            return text(value, context.language)
        case Blank():
            value = 0.0
        case str():
            read = formats.read(value, context.language)
            value = value if read is None else read
    shown = numformat.shown(value, code, context.language.code, context.language.code)
    return VALUE if isinstance(shown, str) and len(shown) > numformat.SHOWN_LONGEST else shown


@form("EXACT")
def exact(context, first, second):
    return first == second


@form("REPT")
def rept(context, value, times):
    if times < 0:
        return VALUE
    return _long(value * math.trunc(times))


@form("CHAR")
def char(context, code):
    code = math.trunc(code)
    if not 1 <= code <= 255:
        return VALUE
    try:
        return bytes([code]).decode(context.language.code_page)
    except UnicodeDecodeError:
        return chr(code)


@form("CODE")
def code_(context, value):
    if not value:
        return VALUE
    return value[0].encode(context.language.code_page, errors="replace")[0]


@form("CLEAN")
def clean(context, value):
    return "".join(each for each in value if ord(each) > 31)


@form("VALUE")
def value_(context, value):
    if isinstance(value, bool):
        return VALUE
    return number(value, context.language)


@form("NUMBERVALUE")
def numbervalue(context, value, decimal=None, group=None):
    """The text read with the marks given, as `formats.read_marked` reads it. A group mark left
    alone, given or the language's, reads as 0; an empty mark is #VALUE!. With no group given,
    the language's own groups, or its decimal mark where the decimal given is its group mark:
    NUMBERVALUE("1.234,5",",") is 1234.5 in English too."""
    if decimal == "" or group == "":
        return VALUE
    marks = formats.marks(context.language.code)
    decimal = (decimal or marks[0])[:1]
    if group is None:
        group = marks[1] if marks[1] != decimal else marks[0]
    group = group[:1]
    if decimal == group:
        return VALUE
    found = formats.read_marked(value, decimal, group, context.language)
    return VALUE if found is None else found


def _split(value, delimiter, instance, mode, end, missing, before: bool):
    instance, mode, end = math.trunc(instance), math.trunc(mode), math.trunc(end)
    if instance == 0 or abs(instance) > len(value) or mode not in (0, 1) or end not in (0, 1):
        return VALUE
    haystack, needle = (value.lower(), delimiter.lower()) if mode else (value, delimiter)
    spans = []
    if needle:
        at = haystack.find(needle)
        while at >= 0:
            spans.append((at, at + len(needle)))
            at = haystack.find(needle, at + len(needle))
    else:
        spans = [(at, at) for at in range(len(value) + 1)]
    if end:
        spans = spans + [(len(value), len(value))] if instance > 0 else [(0, 0), *spans]
    picked = instance - 1 if instance > 0 else instance
    if not -len(spans) <= picked < len(spans):
        return NA if missing is None or isinstance(missing, Blank) else missing
    start, stop = spans[picked]
    return value[:start] if before else value[stop:]


@form("TEXTBEFORE")
def textbefore(context, value, delimiter, instance=1.0, mode=0.0, end=0.0, missing=None):
    return _split(value, delimiter, instance, mode, end, missing, True)


@form("TEXTAFTER")
def textafter(context, value, delimiter, instance=1.0, mode=0.0, end=0.0, missing=None):
    return _split(value, delimiter, instance, mode, end, missing, False)


@form("FIXED")
def fixed(context, value, decimals=2.0, no_commas=False):
    decimals = math.trunc(decimals)
    if decimals > 127:
        return VALUE
    with localcontext(prec=EXACT):
        shown = Decimal(f"{value:.15g}").quantize(Decimal(1).scaleb(-decimals), ROUND_HALF_UP)
    places = max(decimals, 0)
    point, group = formats.marks(context.language.code)
    whole, _, fraction = f"{abs(shown):.{places}f}".partition(".")
    if not no_commas:
        whole = f"{int(whole):,}".replace(",", group)
    written = ("-" if shown < 0 else "") + whole + (point + fraction if places else "")
    return VALUE if len(written) > numformat.SHOWN_LONGEST else written


@form("T")
def t(context, value):
    return value if isinstance(value, str) else ""


def _within(scope, joined: sql.Typed) -> sql.Typed:
    return scope.bound(
        [joined],
        lambda t: sql.Typed(
            f"CASE WHEN length({t[0].sql}) <= {LONGEST} THEN {t[0].sql} END", sql.TEXT
        ),
    )


@sql_form("CONCATENATE")
def concatenate_sql(scope, *texts):
    return _within(scope, sql.Typed("(" + " || ".join(each.sql for each in texts) + ")", sql.TEXT))


def _count(count: sql.Typed) -> str:
    return f"least(trunc({count.sql}), 1e9)::int"


@sql_form("LEFT")
def left_sql(scope, given, count=None):
    count = sql.constant(1.0) if count is None else count
    return sql.Typed(
        f"CASE WHEN {count.sql} >= 0 THEN left({given.sql}, {_count(count)}) END", sql.TEXT
    )


@sql_form("RIGHT")
def right_sql(scope, given, count=None):
    count = sql.constant(1.0) if count is None else count
    return sql.Typed(
        f"CASE WHEN {count.sql} >= 0 THEN right({given.sql}, {_count(count)}) END", sql.TEXT
    )


@sql_form("MID")
def mid_sql(scope, given, start, count):
    return sql.Typed(
        f"CASE WHEN {start.sql} >= 1 AND {count.sql} >= 0 "
        f"THEN substr({given.sql}, {_count(start)}, {_count(count)}) END",
        sql.TEXT,
    )


@sql_form("LEN")
def len_sql(scope, given):
    return sql.Typed(f"length({given.sql})::float8", sql.NUMBER)


@sql_form("TRIM")
def trim_sql(scope, given):
    return sql.Typed(f"btrim(regexp_replace({given.sql}, ' +', ' ', 'g'), ' ')", sql.TEXT)


@sql_form("EXACT")
def exact_sql(scope, first, second):
    return sql.Typed(f"({first.sql} = {second.sql})", sql.LOGICAL)


def _cased(given: sql.Typed, changed: str) -> sql.Typed:
    return sql.Typed(
        f"CASE WHEN {given.sql} ~ {sql.text_literal(sql.CASED_TEXT)} THEN {changed} END", sql.TEXT
    )


@sql_form("UPPER")
def upper_sql(scope, given):
    return _cased(given, sql.uppered(given.sql))


@sql_form("LOWER")
def lower_sql(scope, given):
    return _cased(given, sql.lowered(given.sql))


@sql_form("T")
def t_sql(scope, given):
    if given.known is not sql.UNKNOWN:
        return sql.constant(t(None, given.known))
    if given.kind != sql.VALUE:
        return given if given.kind == sql.TEXT else sql.constant("")
    return sql.Typed(
        f"CASE WHEN jsonb_typeof({given.sql}) = 'string' THEN {given.sql} #>> '{{}}' ELSE '' END",
        sql.TEXT,
    )
