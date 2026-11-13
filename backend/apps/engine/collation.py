"""How Excel compares text: as Windows' CompareString with NORM_IGNORECASE in the installation's
locale, by the weights Microsoft publishes with [MS-UCODEREF] (collation.json.gz, derived from
the Windows 11 Sorting Weight Table by `python -m apps.engine.collation <table>`).

The comparison is no order. Diacritics are summed in a byte, old Hangul jamo weigh only where
both texts have them, and the units both texts begin with are skipped before anything is
weighed, so three texts can stand a < b < c < a. Excel's SORT therefore orders by the merges it
makes (sort), not by a key."""

import base64
import gzip
import hashlib
import json
import struct
import sys
from functools import cache, lru_cache
from pathlib import Path

from .formats import CULTURES

SOURCE = (
    "https://download.microsoft.com/download/C/F/7/CF713A5E-9FBC-4FD6-9246-275F65C0E498/"
    "Windows%2011%20Sorting%20Weight%20Table.txt"
)
DERIVED = Path(__file__).with_name("collation.json.gz")
# Windows weighs the dz digraphs that start a compression of Croatian (a caron after them) by
# two Tibetan weights where none follows, as no section of the table says (its Hungarian
# exception for them reads "get rid of dz bugs"): Excel holds ǲ equal to Tibetan Ba Sa, ǳ to
# Pa O, and sorts Ǳ after Da Nna, where no letter weighs between Nna and Pa (matching-hr.xlsx).
UNWRITTEN = {
    "hr": {
        0x01F1: ((64, 94, 2, 26), (64, 121, 2, 2)),
        0x01F2: ((64, 146, 2, 18), (64, 203, 2, 2)),
        0x01F3: ((64, 135, 2, 2), (64, 223, 2, 2)),
    }
}
# Excel compares German and French texts off the quick path, though the table gives them
# neither exceptions nor compressions: it holds x equal to x and a soft hyphen, and a kana repeat
# mark after x weighs as x (matching-de.xlsx, matching-fr.xlsx).
UNHURRIED = frozenset({"de", "fr"})

UNSORTABLE, NONSPACE, EXPANSION, EASTASIA, JAMO, EXT_A, PUNCT = range(7)
MAX_SPECIAL = 11
KANA = 34
IGNORECASE = 0xE7
FIRST_SYLLABLE = 0xAC00
FILLER = 0x115F
TAG = 0xDB40
SELECTORS = range(0xDD00, 0xDDF0)


class _Key:
    """What CompareString weighs of a text: the primary weights, the extra weights of old Hangul
    jamo by where they stand in them, each character's diacritic with its marks, the cases and
    what is left (the kana's extra weights and the punctuation it weighs last). It is steady
    where nothing in the text weighs by what stands before it or weighs nothing: the
    comparison of such texts is the comparison of their keys from the first unit on."""

    __slots__ = ("primary", "jamo", "diacritics", "cases", "rest", "steady", "reverse")

    def __init__(self, primary, jamo, diacritics, cases, rest, steady, reverse):
        self.primary, self.jamo, self.diacritics = primary, jamo, diacritics
        self.cases, self.rest, self.steady, self.reverse = cases, rest, steady, reverse

    def compare(self, other: _Key) -> int:
        a, b = self.primary, other.primary
        n = min(len(a), len(b))
        p = 0
        while p < n and a[p] == b[p]:
            p += 1
        for at in sorted(self.jamo.keys() & other.jamo.keys()):
            if at + 2 > p:
                break
            if self.jamo[at] != other.jamo[at]:
                return -1 if self.jamo[at] < other.jamo[at] else 1
        if p < n:
            return -1 if a[p] < b[p] else 1
        if len(a) != len(b):
            return -1 if len(a) < len(b) else 1
        diacritics = self.diacritics, other.diacritics
        if self.reverse:
            diacritics = _backward(*diacritics, [2])
        if found := _padded(*diacritics, [2], _marked):
            return found
        if found := _padded(self.cases, other.cases, 2, _ordered):
            return found
        return _ordered(self.rest, other.rest)


def _ordered(a, b) -> int:
    return (a > b) - (a < b)


def _marked(a: list[int], b: list[int]) -> int:
    """Two characters' diacritics: where theirs differ, each summed with its marks in a byte;
    where theirs agree, the marks alone."""
    if a[0] != b[0]:
        return _ordered(sum(a) & 0xFF, sum(b) & 0xFF)
    return _ordered(sum(a[1:]) & 0xFF, sum(b[1:]) & 0xFF)


def _trimmed(given: list, pad) -> list:
    end = len(given)
    while end and given[end - 1] == pad:
        end -= 1
    return given[:end]


def _backward(a: list, b: list, pad) -> tuple[list, list]:
    """Two texts' weights from the last to the first, as a locale that reverses diacritics
    weighs them (French)."""
    n = max(len(a), len(b))
    return [*a, *[pad] * (n - len(a))][::-1], [*b, *[pad] * (n - len(b))][::-1]


def _padded(a: list, b: list, pad, compare) -> int:
    for at in range(max(len(a), len(b))):
        if found := compare(a[at] if at < len(a) else pad, b[at] if at < len(b) else pad):
            return found
    return 0


def _units(text: str) -> tuple[int, ...]:
    data = text.encode("utf-16-le", "surrogatepass")
    return struct.unpack(f"<{len(data) // 2}H", data)


class Collation:
    """CompareString in one locale."""

    def __init__(self, code: str):
        table = _table()
        self._weights, self._present = table["weights"], table["present"]
        self._expansion, self._compatibility = table["expansion"], table["compatibility"]
        self._jamo = table["jamo"]
        locale = table["locales"][code]
        self._unwritten = UNWRITTEN.get(code, {})
        self._exception = {
            **locale["exception"],
            **{unit: weights[0] for unit, weights in self._unwritten.items()},
        }
        self._compression = locale["compression"]
        self._reverse = locale["reverse"]
        self._starts: dict[int, list[int]] = {}
        for units in self._compression:
            self._starts.setdefault(units[0], []).append(len(units))
        for sizes in self._starts.values():
            sizes.sort(reverse=True)
        # A locale with neither exceptions nor compressions takes CompareString's quick path:
        # an empty rest after the shared start is less, whatever the other's rest weighs.
        self._quick = code not in UNHURRIED and not self._exception and not self._compression
        self.key = lru_cache(maxsize=1 << 16)(self._key)

    @property
    def compressions(self):
        """The runs of units the locale weighs as one letter."""
        return self._compression.keys()

    def compare(self, left: str, right: str) -> int:
        a, b = _units(left), _units(right)
        p = self._shared(a, b)
        a, b = a[p:], b[p:]
        if self._quick and (not a or not b):
            return _ordered(len(a), len(b))
        return self.key(a).compare(self.key(b))

    def matches(self, left: str, right: str) -> bool:
        """Whether two texts are of as many units and equal weighed from the first unit on, as
        a lookup matches each run of its pattern (criteria.fits)."""
        a, b = _units(left), _units(right)
        return len(a) == len(b) and self.key(a).compare(self.key(b)) == 0

    def equality(self, text: str) -> bytes | None:
        """A key two texts share exactly where compare holds them equal; None for a text that
        is not steady, which compare may hold equal to texts unequal to each other."""
        key = self.key(_units(text))
        if not key.steady:
            return None
        extra, punctuation = key.rest
        parts = (
            key.primary,
            bytes(sum(each) & 0xFF for each in _trimmed(key.diacritics, [2])),
            bytes(_trimmed(key.cases, 2)),
            extra,
            b"".join((-at).to_bytes(4) + bytes(weights) for at, *weights in punctuation),
        )
        return b"".join(len(part).to_bytes(4) + part for part in parts)

    def ranks(self, texts) -> dict[str, float] | None:
        """Each text's place among them in the order compare gives, equal texts sharing one;
        None where that is no order: a text not steady, or one whose diacritic and marks sum
        past the byte they are weighed in."""
        keys = {}
        for text in texts:
            key = self.key(_units(text))
            if not key.steady or any(sum(each) > 0xFF for each in key.diacritics):
                return None
            keys[text] = key
        marks = max((len(key.diacritics) for key in keys.values()), default=0)
        cases = max((len(key.cases) for key in keys.values()), default=0)
        ordered = {
            text: (
                key.primary,
                self._diacritics(key, marks),
                bytes(key.cases) + b"\x02" * (cases - len(key.cases)),
                key.rest[0],
                tuple(key.rest[1]),
            )
            for text, key in keys.items()
        }
        places = {key: float(at) for at, key in enumerate(sorted(set(ordered.values())))}
        return {text: places[key] for text, key in ordered.items()}

    def _diacritics(self, key: _Key, marks: int) -> bytes:
        """A key's diacritics summed with their marks, as many as `marks`, in the order the
        locale weighs them."""
        summed = [sum(each) for each in key.diacritics] + [2] * (marks - len(key.diacritics))
        return bytes(summed[::-1] if self._reverse else summed)

    def _shared(self, a: tuple[int, ...], b: tuple[int, ...]) -> int:
        """How many units both texts begin with CompareString skips: ASCII ones that start no
        compression, less the last where a unit after it weighs by what stands before it."""
        n = min(len(a), len(b))
        p = 0
        while p < n and a[p] == b[p] and a[p] < 0x80 and a[p] not in self._starts:
            p += 1
        if p and any(p < len(x) and self._leans(x[p]) for x in (a, b)):
            p -= 1
        return p

    def _leans(self, unit: int) -> bool:
        kind, alphabetic, _, _ = self._weighed(unit)
        if self._quick:
            return kind == NONSPACE
        return kind == NONSPACE or kind == EASTASIA and alphabetic <= 1

    def _weighed(self, unit: int) -> tuple[int, int, int, int]:
        while True:
            if unit in self._exception:
                return self._exception[unit]
            if self._present[unit]:
                return tuple(self._weights[unit * 4 : unit * 4 + 4])
            if unit in self._compatibility:
                unit = self._compatibility[unit]
                continue
            if unit in self._expansion:
                return EXPANSION, 0, 0, 0
            return UNSORTABLE, 0, 0, 0

    def _expanded(self, unit: int) -> list[tuple[int, int, int, int]]:
        while unit not in self._expansion:
            unit = self._compatibility[unit]
        first, second = self._expansion[unit]
        found = [self._weighed(first)]
        last = self._weighed(second)
        if last[0] == EXPANSION:
            while second not in self._expansion:
                second = self._compatibility[second]
            third, fourth = self._expansion[second]
            found.append(self._weighed(third))
            last = self._weighed(fourth)
        found.append(last)
        return found

    def _flat(self, unit: int, out: list[int]) -> None:
        if unit in self._exception or self._present[unit]:
            out.append(unit)
        elif unit in self._compatibility:
            self._flat(self._compatibility[unit], out)
        elif unit in self._expansion:
            first, second = self._expansion[unit]
            self._flat(first, out)
            self._flat(second, out)

    def _key(self, given: tuple[int, ...]) -> _Key:
        units: list[int] = []
        tagged = False
        steady = True
        for unit in given:
            if tagged and unit in SELECTORS:
                tagged = False
                continue
            tagged = unit == TAG
            steady &= not tagged
            if not tagged:
                before = len(units)
                self._flat(unit, units)
                steady &= len(units) > before
        primary: list[tuple] = []
        diacritics: list[list[int]] = []
        cases: list[int] = []
        kana: list[tuple[int, int, int, int]] = []
        punctuation: list[tuple] = []
        jamo: dict[int, tuple[int, int, int]] = {}
        at = 0
        n = len(units)
        while at < n:
            unit = units[at]
            kind, alphabetic, diacritic, case = self._weighed(unit)
            if kind > MAX_SPECIAL:
                compressed = next(
                    (
                        (size, weight)
                        for size in self._starts.get(unit, ())
                        if at + size <= n
                        and (weight := self._compression.get(tuple(units[at : at + size])))
                    ),
                    None,
                )
                if compressed:
                    size, (kind, alphabetic, diacritic, case) = compressed
                    primary.append((kind, alphabetic))
                    diacritics.append([diacritic])
                    cases.append(case & IGNORECASE)
                    at += size
                    continue
                if unit in self._unwritten:
                    for kind, alphabetic, diacritic, case in self._unwritten[unit]:
                        primary.append((kind, alphabetic))
                        diacritics.append([diacritic])
                        cases.append(case & IGNORECASE)
                    at += 1
                    continue
                # Planes 2 and 3 open with a weight above every CJK one of the first plane.
                if kind == 254 and 0xD800 <= unit <= 0xDBFF:
                    primary += [(254, 255), (kind, alphabetic)]
                    diacritics.append([diacritic])
                elif 169 <= kind <= 175:
                    primary.append((kind, alphabetic, diacritic))
                else:
                    primary.append((kind, alphabetic))
                    diacritics.append([diacritic])
                cases.append(case & IGNORECASE)
            elif kind == NONSPACE:
                if diacritics:
                    diacritics[-1].append(diacritic)
                else:
                    diacritics.append([diacritic])
            elif kind == EXPANSION:
                for kind, alphabetic, diacritic, case in self._expanded(unit):
                    primary.append((kind, alphabetic))
                    diacritics.append([diacritic])
                    cases.append(case & IGNORECASE)
            elif kind == PUNCT:
                punctuation.append((-len(primary), kind, alphabetic, diacritic, case & IGNORECASE))
            elif kind >= 7:
                primary.append((kind, alphabetic))
                diacritics.append([diacritic])
                cases.append(case & IGNORECASE)
            elif kind == EXT_A:
                primary += [(254, 255), (alphabetic, diacritic)]
                diacritics.append([2])
                cases.append(2)
            elif kind == JAMO:
                steady = False
                self._jamo_weighed(unit, primary, jamo)
                diacritics.append([2])
                cases.append(2)
            elif kind == EASTASIA:
                steady &= alphabetic > 1
                diacritic = self._kana(units, at, alphabetic, diacritic, case, primary, kana)
                diacritics.append([diacritic])
                cases.append(2)
            else:
                steady = False
            at += 1
        weights = bytearray()
        for weight in primary:
            weights += bytes(weight if len(weight) == 2 or weight[2] else weight[:2])
        extra = bytearray()
        if kana:
            for place, low in ((0, 0xC4), (1, 3), (2, 0xC4), (3, 0xC4)):
                found = [each[place] for each in kana]
                while len(found) > 1 and found[-1] == low:
                    found.pop()
                extra += bytes(found)
                extra.append(0xFF)
        extra += b"\x01\x00"
        rest = (bytes(extra), punctuation)
        return _Key(bytes(weights), jamo, diacritics, cases, rest, steady, self._reverse)

    def _jamo_weighed(self, unit: int, primary: list[tuple], jamo: dict) -> None:
        """A conjoining jamo as its own element: a leading consonant weighs as the first
        syllable it leads, a vowel and a trailing consonant as the filler's, with the extra
        weight that tells old jamo apart where they stand in the primary weights."""
        old, lead, vowel, trail, extra, kind = self._jamo[unit]
        if kind != "L":
            old, lead, vowel, trail, _, _ = self._jamo[FILLER]
        syllable = FIRST_SYLLABLE + (lead * 21 + vowel) * 28 + trail - 1
        at = sum(2 if len(weight) == 2 or not weight[2] else 3 for weight in primary)
        primary.append(self._weighed(syllable)[:2] if syllable >= FIRST_SYLLABLE else (192, 2))
        if kind == "V":
            jamo[at] = (0x7F, extra, 0)
        elif kind == "T":
            jamo[at] = (0x7F, 3, extra)
        elif old:
            jamo[at] = (extra, 3, 0)

    def _kana(self, units, at, alphabetic, diacritic, case, primary, kana) -> int:
        """A kana's weights; a repeat or a prolonged sound mark weighs as the kana before it,
        and as the highest weight where none stands before it. Returns its diacritic."""
        extra = (case & IGNORECASE) | 0xC4
        if alphabetic > 1:
            primary.append((KANA, alphabetic))
            kana.append((extra & 0xC6, 3, extra & 0xE4, extra & 0xC5))
            return diacritic
        weight = (255, 255)
        before = at - 1
        while before >= 0:
            kind, previous, _, previous_case = self._weighed(units[before])
            if kind < EASTASIA and kind != EXPANSION or kind == EASTASIA and previous <= 1:
                before -= 1
                continue
            if kind == EASTASIA:
                weight = (KANA, previous if alphabetic == 0 else previous & 0x87)
                prior = (previous_case & IGNORECASE) | 0xC4
                kana.append(
                    (
                        prior & 0xC6,
                        4 if alphabetic == 0 else 5,
                        prior & 0xE4,
                        (extra if alphabetic else prior) & 0xC5,
                    )
                )
            else:
                weight = (kind, previous)
            break
        else:
            diacritic = 2
        primary.append(weight)
        return diacritic


@cache
def collation(code: str) -> Collation:
    return Collation(code)


def sort(items: list, compare) -> list:
    """Items in the order Excel's SORT gives them: merged as runs of one, two, four and on,
    each merge taking the right item only where it is less than the left one."""
    runs = [[item] for item in items]
    while len(runs) > 1:
        merged = []
        for at in range(0, len(runs) - 1, 2):
            left, right = runs[at], runs[at + 1]
            out = []
            i = j = 0
            while i < len(left) and j < len(right):
                if compare(left[i], right[j]) <= 0:
                    out.append(left[i])
                    i += 1
                else:
                    out.append(right[j])
                    j += 1
            merged.append(out + left[i:] + right[j:])
        if len(runs) % 2:
            merged.append(runs[-1])
        runs = merged
    return runs[0] if runs else []


@cache
def _table() -> dict:
    with gzip.open(DERIVED, "rt", encoding="utf-8") as derived:
        given = json.load(derived)
    return {
        "weights": base64.b64decode(given["weights"]),
        "present": [
            bool(b >> bit & 1) for b in base64.b64decode(given["present"]) for bit in range(8)
        ],
        "expansion": {int(unit): tuple(pair) for unit, pair in given["expansion"].items()},
        "compatibility": {int(unit): target for unit, target in given["compatibility"].items()},
        "jamo": {int(unit): tuple(row) for unit, row in given["jamo"].items()},
        "locales": {
            code: {
                "exception": {int(unit): tuple(w) for unit, w in locale["exception"].items()},
                "compression": {tuple(row[:-4]): tuple(row[-4:]) for row in locale["compression"]},
                "reverse": locale["reverse"],
            }
            for code, locale in given["locales"].items()
        },
    }


_COUNTS = {"TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6, "SEVEN": 7, "EIGHT": 8}
_SECTIONS = {
    "DEFAULT",
    "RELEASE",
    "REVERSEDIACRITICS",
    "DOUBLECOMPRESSION",
    "INVERSECASING",
    "MULTIPLEWEIGHTS",
    "EXPANSION",
    "COMPATIBILITY",
    "COMPRESSION",
    "EXCEPTION",
    "JAMOSORT",
}


def derive(source: Path) -> dict:
    """The parts of Microsoft's table the cultures of the document languages weigh by."""
    weights = bytearray(0x10000 * 4)
    present = bytearray(0x10000 // 8)
    expansion, compatibility, jamo = {}, {}, {}
    exceptions, compressions, named = {}, {}, {}
    section = guid = width = None
    for raw in source.read_text(encoding="utf-8-sig").splitlines():
        line, _, note = raw.partition(";")
        fields = line.split()
        if not fields:
            continue
        head = fields[0]
        if head in ("SORTKEY", "SORTTABLES", "ENDSORTKEY", "ENDSORTTABLES"):
            section = None
        elif head in _SECTIONS:
            section, guid = head, None
        elif head == "SORTGUID":
            guid, width = (fields[1], " ".join(fields[2:])), None
        elif head == "LOCALENAME":
            named.setdefault(fields[1], {})[section] = guid
        elif head in _COUNTS:
            width = _COUNTS[head]
        elif head.startswith("0x"):
            unit = int(head, 16)
            if section == "DEFAULT":
                weights[unit * 4 : unit * 4 + 4] = bytes(int(x) for x in fields[1:5])
                present[unit // 8] |= 1 << unit % 8
            elif section == "EXPANSION":
                expansion[unit] = [int(fields[1], 16), int(fields[2], 16)]
            elif section == "COMPATIBILITY":
                compatibility[unit] = int(fields[1], 16)
            elif section == "JAMOSORT":
                jamo[unit] = [*(int(x, 16) for x in fields[1:6]), note.split()[1]]
            elif section == "EXCEPTION":
                exceptions.setdefault(guid, {})[unit] = [int(x) for x in fields[1:5]]
            elif section == "COMPRESSION":
                row = [int(x, 16) for x in fields[:width]] + [
                    int(x) for x in fields[width : width + 4]
                ]
                compressions.setdefault(guid[0], []).append(row)
    locales = {}
    for code, name in CULTURES.items():
        entry = named.get(name, {})
        exception = entry.get("EXCEPTION")
        if exception and "LINGUISTIC_CASING" in exception[1]:
            raise ValueError(f"{name} cases by its language, which the engine does not weigh")
        unweighed = entry.keys() - {"EXCEPTION", "COMPRESSION", "REVERSEDIACRITICS"}
        if unweighed:
            raise ValueError(f"{name} weighs by {sorted(unweighed)}, which the engine does not")
        locales[code] = {
            "exception": exceptions.get(exception, {}),
            "compression": compressions.get(entry["COMPRESSION"][0], [])
            if "COMPRESSION" in entry
            else [],
            "reverse": "REVERSEDIACRITICS" in entry,
        }
    return {
        "source": SOURCE,
        "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "weights": base64.b64encode(weights).decode(),
        "present": base64.b64encode(present).decode(),
        "expansion": expansion,
        "compatibility": compatibility,
        "jamo": jamo,
        "locales": locales,
    }


if __name__ == "__main__":
    derived = json.dumps(derive(Path(sys.argv[1])), separators=(",", ":"), sort_keys=True)
    DERIVED.write_bytes(gzip.compress(derived.encode(), mtime=0))
