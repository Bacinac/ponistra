"""How a help article is written: its files, its fixed headings and the marks that tie its text to
the code. The library serves what this reads and scripts/help.py checks it, outside Django, so
only the standard library stands here."""

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

LANGUAGES = ("hr", "en")
HEADINGS = {
    "hr": ("Kako se koristi", "Kako radi", "Ograničenja", "Povezano"),
    "en": ("How to use it", "How it works", "Limits", "Related"),
}
LABEL = re.compile(r"\{t:([^}\s]+)\}")
KEYS = re.compile(r"\{k:([^}\s]+)\}")
LINK = re.compile(r"\]\(help:([\w-]+/[\w-]+)\)")
PAGE = re.compile(r"\]\((/[^)\s]*)\)")
SHOT = re.compile(r"!\[([^\]]*)\]\(shot:([\w-]+)\)")
_MESSAGE = re.compile(
    r"""^\s*'([^']+)':\s*('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|`(?:[^`\\]|\\.)*`)""", re.M
)
_ESCAPE = re.compile(r"\\(.)")
_SIGNS = {"Mod": "Ctrl"}


def messages(path: Path) -> dict[str, str]:
    """A language's interface strings out of frontend/src/i18n, by key."""
    return {
        key: _ESCAPE.sub(r"\1", value[1:-1]) for key, value in _MESSAGE.findall(path.read_text())
    }


def shortcut(keys: str) -> str:
    """As frontend/src/keys.ts shows it off Apple's devices, which the page corrects for theirs."""
    *held, key = keys.split("-")
    return "+".join(
        [*(_SIGNS.get(each, each) for each in held), key.upper() if len(key) == 1 else key]
    )


def fold(text: str) -> str:
    """Lower case, without the marks a search should not have to type."""
    plain = unicodedata.normalize("NFKD", text.replace("đ", "d").replace("Đ", "D"))
    return "".join(each for each in plain if not unicodedata.combining(each)).casefold()


@dataclass(frozen=True)
class Written:
    """An article's two files and the record beside them, as they stand on disk."""

    id: str
    record: dict
    bodies: dict[str, str]


def sections(folder: Path) -> list[dict]:
    return json.loads((folder / "sections.json").read_text())


def written(folder: Path) -> list[Written]:
    found = []
    for record in sorted(folder.glob("*/*.json")):
        identifier = f"{record.parent.name}/{record.stem}"
        bodies = {}
        for language in LANGUAGES:
            body = record.with_name(f"{record.stem}.{language}.md")
            bodies[language] = body.read_text() if body.exists() else ""
        found.append(Written(identifier, json.loads(record.read_text()), bodies))
    return found


def title_of(body: str) -> str:
    first = body.split("\n", 1)[0]
    return first[2:].strip() if first.startswith("# ") else ""


def summary_of(body: str) -> str:
    """The paragraph under the title, which says in a sentence what the article is about."""
    paragraphs = body.split("\n\n")
    return " ".join(paragraphs[1].split()) if len(paragraphs) > 1 else ""


def parts_of(body: str) -> list[tuple[str, str]]:
    """The second-level headings in order, each with the text under it."""
    pieces = re.split(r"^## (.+)$", body, flags=re.M)
    return [(pieces[at].strip(), pieces[at + 1].strip()) for at in range(1, len(pieces) - 1, 2)]
