"""The help as a reader gets it: the articles in help/, shipped with each release, their interface
names and shortcuts filled in from the strings of that same release."""

import re
from dataclasses import dataclass
from functools import cache
from html import escape
from pathlib import Path

from django.conf import settings
from markdown_it import MarkdownIt

from . import source

_RENDERER = MarkdownIt("commonmark", {"html": True}).enable("table")
FALLBACK = "hr"


@dataclass(frozen=True)
class Page:
    title: str
    summary: str
    reading: str
    html: str
    title_words: str
    summary_words: str
    body_words: str


@dataclass(frozen=True)
class Article:
    id: str
    section: str
    order: int
    admin: bool
    screens: tuple[str, ...]
    pages: dict[str, Page]


@dataclass(frozen=True)
class Library:
    sections: tuple[dict, ...]
    articles: dict[str, Article]


def _filled(body: str, labels: dict[str, str]) -> str:
    named = source.LABEL.sub(lambda found: f"**{labels[found[1]]}**", body)
    return re.sub(r"\]\(help:", "](/help/", named)


def _reading(body: str, labels: dict[str, str]) -> str:
    """What an agent reads: Markdown, without the pictures it could not open."""
    text = source.SHOT.sub("", _filled(body, labels))
    return source.KEYS.sub(lambda found: f"`{source.shortcut(found[1])}`", text).strip()


def _html(body: str, labels: dict[str, str]) -> str:
    text = source.KEYS.sub(
        lambda found: f'<kbd data-keys="{escape(found[1])}">{source.shortcut(found[1])}</kbd>',
        _filled(body, labels),
    )
    text = source.SHOT.sub(
        lambda found: f'<img data-shot="{found[2]}" alt="{escape(found[1])}">',
        text,
    )
    return _RENDERER.render(text.split("\n\n", 2)[2])


def _page(body: str, labels: dict[str, str]) -> Page:
    filled = _filled(body, labels)
    title = source.title_of(filled)
    summary = source.summary_of(filled).replace("**", "")
    return Page(
        title,
        summary,
        _reading(body, labels),
        _html(body, labels),
        source.fold(title),
        source.fold(summary),
        source.fold(filled),
    )


@cache
def _read(folder: Path, i18n: Path, _state: tuple) -> Library:
    labels = {each: source.messages(i18n / f"{each}.ts") for each in source.LANGUAGES}
    sections = source.sections(folder)
    places = {section["id"]: at for at, section in enumerate(sections)}
    articles = [
        Article(
            each.id,
            each.id.split("/")[0],
            each.record["order"],
            each.record["audience"] == "admin",
            tuple(
                cover.removeprefix("route:")
                for cover in each.record.get("covers", [])
                if cover.startswith("route:")
            ),
            {
                language: _page(each.bodies[language], labels[language])
                for language in source.LANGUAGES
            },
        )
        for each in source.written(folder)
    ]
    articles.sort(key=lambda each: (places[each.section], each.order, each.id))
    return Library(tuple(sections), {each.id: each for each in articles})


def library() -> Library:
    folder, i18n = Path(settings.HELP), Path(settings.I18N)
    files = [*folder.glob("*/*"), folder / "sections.json", *i18n.glob("*.ts")]
    # Each release's are fixed; in a dev tree they change under a running server.
    return _read(
        folder, i18n, tuple(sorted((str(each), each.stat().st_mtime_ns) for each in files))
    )


def _readable(user, every: Library) -> list[Article]:
    return [each for each in every.articles.values() if user.is_staff or not each.admin]


def language_of(asked: str | None, user) -> str:
    for each in (asked, user.language):
        if each in source.LANGUAGES:
            return each
    return FALLBACK


def contents(user, language: str) -> dict:
    """The sections in order with their articles, and which article is about which screen."""
    every = library()
    labels = source.messages(Path(settings.I18N) / f"{language}.ts")
    readable = _readable(user, every)
    sections = []
    for section in every.sections:
        articles = [
            {
                "id": each.id,
                "title": each.pages[language].title,
                "summary": each.pages[language].summary,
            }
            for each in readable
            if each.section == section["id"]
        ]
        if articles:
            sections.append(
                {
                    "id": section["id"],
                    "title": labels[f"help.section.{section['id']}"],
                    "articles": articles,
                }
            )
    screens = [{"path": path, "article": each.id} for each in readable for path in each.screens]
    return {"sections": sections, "screens": screens}


def article(user, identifier: str, language: str) -> Page | None:
    found = library().articles.get(identifier)
    if found is None or (found.admin and not user.is_staff):
        return None
    return found.pages[language]


def _stem(word: str) -> str:
    """Enough of a word to find it however Croatian ends it: odgoda, odgodi, odgodu."""
    return word[: max(4, len(word) - 2)] if len(word) > 4 else word


def found(user, text: str, language: str, limit: int) -> list[dict]:
    """The articles holding every word asked for, those with it in the title first."""
    words = [re.compile(rf"\b{re.escape(_stem(each))}") for each in source.fold(text).split()]
    scored = []
    for each in _readable(user, library()):
        page = each.pages[language]
        if not words or not all(word.search(page.body_words) for word in words):
            continue
        score = sum(
            3 * bool(word.search(page.title_words)) + bool(word.search(page.summary_words))
            for word in words
        )
        scored.append((-score, each.id, page))
    scored.sort(key=lambda each: each[:2])
    return [
        {"id": identifier, "title": page.title, "summary": page.summary}
        for _, identifier, page in scored[:limit]
    ]
