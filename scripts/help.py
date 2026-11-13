"""The help's gate, run by scripts/help.sh in the backend's image with the tree at /tree.

  help.py check            what a push waits for: every article whole in both languages, each thing
                           the interface offers covered by one, none describing code that has
                           changed since it was last read
  help.py seen <article>…  after reading an article against the changed code: note the code as read
  help.py gaps [prefix…]   what no article covers yet, as `help/uncovered.txt` holds it
  help.py sync             takes what has since been covered out of help/uncovered.txt

What must be covered is read from the code, so nothing new can arrive without a place in the help:
the routes of App.tsx, the settings of settings.tsx, the actions of the registry, the agents' tools,
and each interface string, which an article names as {t:key} or lists under `quiet`."""

import fnmatch
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

TREE = Path("/tree")
HELP = TREE / "help"
I18N = TREE / "frontend/src/i18n"
IGNORED = HELP / "ignored.txt"
UNCOVERED = HELP / "uncovered.txt"
AUDIENCES = {"everyone", "admin"}
ROUTE = re.compile(r'<Route path="([^"]+)"')
SETTING = re.compile(r"to: '(/settings/[^']+)'")
ACTION = re.compile(r'Action\(\s*"([\w.]+)"')
TOOL = re.compile(r"@server\.tool\(\)\s*\n(?:async )?def (\w+)")
SHOT_MADE = re.compile(r"""\bshot\(\s*'([\w-]+)'""")
STEP = re.compile(r"^\d+\. ", re.M)
BULLET = re.compile(r"^- ", re.M)
SUBHEADING = re.compile(r"^### ", re.M)


def loaded(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


source = loaded("help_source", TREE / "backend/apps/help/source.py")
selection = loaded("gate_select", TREE / "scripts/select.py")


def inventory() -> dict[str, str]:
    """All that must have a place in the help, each with what to show of it."""
    code = (TREE / "frontend/src/App.tsx").read_text()
    settings = (TREE / "frontend/src/settings.tsx").read_text()
    actions = (TREE / "backend/apps/actions/registry.py").read_text()
    tools = (TREE / "backend/apps/agents/tools.py").read_text()
    found = {f"route:{path}": "" for path in ROUTE.findall(code)}
    found |= {f"setting:{path}": "" for path in SETTING.findall(settings)}
    found |= {f"action:{name}": "" for name in ACTION.findall(actions)}
    found |= {f"tool:{name}": "" for name in TOOL.findall(tools)}
    found |= {f"label:{key}": text for key, text in source.messages(I18N / "hr.ts").items()}
    return found


def ignored() -> list[str]:
    if not IGNORED.exists():
        return []
    lines = (line.split("#", 1)[0].strip() for line in IGNORED.read_text().splitlines())
    return [line for line in lines if line]


def listed(file: Path) -> set[str]:
    return set(file.read_text().split("\n")) - {""} if file.exists() else set()


def covered_by(articles) -> set[str]:
    found = set()
    for article in articles:
        found |= set(article.record.get("covers", []))
        found |= {f"label:{key}" for key in article.record.get("quiet", [])}
        for body in article.bodies.values():
            found |= {f"label:{key}" for key in source.LABEL.findall(body)}
    return found


def open_items(items: dict[str, str], articles) -> list[str]:
    covered = covered_by(articles)
    skipped = ignored()
    return sorted(
        item
        for item in items
        if item not in covered and not any(fnmatch.fnmatchcase(item, each) for each in skipped)
    )


def fingerprint(described: str) -> str | None:
    """The code an article describes as it stands: a file's top-level function, class or value, or
    the whole of a file named alone. None when it is gone."""
    path, _, name = described.partition("#")
    file = TREE / path
    if not file.exists():
        return None
    text = file.read_text()
    if name:
        lines = text.splitlines()
        for first, last, _kind, found in selection.units(path):
            if found == name:
                text = "\n".join(lines[first - 1 : last])
                break
        else:
            return None
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def body_problems(article, language: str, labels: dict[str, str], known) -> list[str]:
    body = article.bodies[language]
    if not body:
        return [f"{language}: file missing"]
    found = []
    if not source.title_of(body):
        found.append(f"{language}: must start with `# Title`")
    summary = source.summary_of(body)
    if not summary or summary[0] in "#-!|" or STEP.match(summary):
        found.append(f"{language}: the paragraph under the title must say what the article is about")
    parts = source.parts_of(body)
    if tuple(heading for heading, _ in parts) != source.HEADINGS[language]:
        found.append(f"{language}: headings must be exactly {source.HEADINGS[language]}")
    for heading, text in parts:
        if not text:
            found.append(f"{language}: `## {heading}` is empty")
    if parts and parts[-1][0] == source.HEADINGS[language][-1] and not source.LINK.search(parts[-1][1]):
        found.append(f"{language}: `## {parts[-1][0]}` must link to at least one article")
    plain = source.LABEL.sub("", body)
    if "**" in plain:
        found.append(f"{language}: bold is for interface names only, written {{t:key}}")
    for key in source.LABEL.findall(body):
        if key not in labels:
            found.append(f"{language}: no interface string {key}")
        elif "{" in labels[key]:
            found.append(f"{language}: {key} takes values; list it under quiet, describe it in words")
    for key, mark in re.findall(r"\{t:([^}]+)\}([.,:;!?])", body):
        if labels.get(key, "")[-1:] in {".", "!", "?", ":", "…"}:
            found.append(f"{language}: {key} ends in its own mark; {mark} after it doubles it")
    for target in source.LINK.findall(body):
        if target not in known["articles"]:
            found.append(f"{language}: no article {target}")
        elif article.record.get("audience") == "everyone" and target in known["admin"]:
            found.append(f"{language}: {target} is for administrators, this article for everyone")
    for page in source.PAGE.findall(body):
        if not known["pages"].fullmatch(page.split("?")[0]):
            found.append(f"{language}: no page at {page}")
    for _, shot in source.SHOT.findall(body):
        if shot not in known["shots"]:
            found.append(f"{language}: no shot `{shot}` is made in e2e/shots")
    return found


def shape(body: str) -> dict:
    return {
        "labels": set(source.LABEL.findall(body)),
        "shortcuts": set(source.KEYS.findall(body)),
        "links": set(source.LINK.findall(body)),
        "pages": set(source.PAGE.findall(body)),
        "shots": {shot for _, shot in source.SHOT.findall(body)},
        "subheadings": len(SUBHEADING.findall(body)),
        "steps": len(STEP.findall(body)),
        "bullets": len(BULLET.findall(body)),
    }


def known_things(articles, sections) -> dict:
    routes = ROUTE.findall((TREE / "frontend/src/App.tsx").read_text())
    patterns = []
    for route in routes:
        if route != "*":
            pattern = re.sub(r"/:[^/]+\?", "(/[^/]+)?", route)
            patterns.append(re.sub(r":[^/(]+", "[^/]+", pattern))
    shots = set()
    for file in (TREE / "e2e/shots").glob("*.ts") if (TREE / "e2e/shots").exists() else []:
        shots |= set(SHOT_MADE.findall(file.read_text()))
    return {
        "articles": {article.id for article in articles},
        "admin": {each.id for each in articles if each.record.get("audience") == "admin"},
        "pages": re.compile("|".join(patterns)),
        "shots": shots,
        "sections": {section["id"] for section in sections},
    }


def check() -> list[str]:
    articles = source.written(HELP)
    sections = source.sections(HELP)
    known = known_things(articles, sections)
    items = inventory()
    labels = {language: source.messages(I18N / f"{language}.ts") for language in source.LANGUAGES}
    problems = []
    screens: dict[str, str] = {}
    for article in articles:
        said = []
        record = article.record
        if article.id.split("/")[0] not in known["sections"]:
            said.append("its folder is not in sections.json")
        if record.get("audience") not in AUDIENCES:
            said.append(f"audience must be one of {sorted(AUDIENCES)}")
        if not isinstance(record.get("order"), int):
            said.append("order must be a number")
        if not record.get("describes"):
            said.append("describes names no code")
        for language in source.LANGUAGES:
            said += body_problems(article, language, labels[language], known)
        shapes = {language: shape(article.bodies[language]) for language in source.LANGUAGES}
        for part, hr in shapes["hr"].items():
            if hr != shapes["en"][part]:
                said.append(f"hr and en differ in {part}: {hr} / {shapes['en'][part]}")
        for item in record.get("covers", []):
            if item not in items:
                said.append(f"covers {item}, which the code no longer has")
            if item.startswith("route:"):
                if item in screens:
                    said.append(f"{item} is already the screen of {screens[item]}")
                screens[item] = article.id
        for key in record.get("quiet", []):
            if f"label:{key}" not in items:
                said.append(f"quiet names {key}, which the code no longer has")
        for described, seen in record.get("describes", {}).items():
            now = fingerprint(described)
            if now is None:
                said.append(f"describes {described}, which no longer exists: correct `describes`")
            elif now != seen:
                said.append(
                    f"{described} changed since this was read: read the article against it, "
                    f"correct what no longer holds, then `scripts/help.sh seen {article.id}`"
                )
        problems += [f"help/{article.id}: {each}" for each in said]
    waiting = listed(UNCOVERED)
    still = set(open_items(items, articles))
    problems += [
        f"{item} has no place in the help: name it in an article (help/README.md)"
        for item in sorted(still - waiting)
    ]
    problems += [
        f"{item} is covered or gone: `scripts/help.sh sync`" for item in sorted(waiting - still)
    ]
    return problems


def seen(wanted: list[str]) -> None:
    for identifier in wanted:
        path = HELP / f"{identifier}.json"
        record = json.loads(path.read_text())
        for described in record["describes"]:
            now = fingerprint(described)
            if now is None:
                sys.exit(f"{identifier}: {described} does not exist")
            record["describes"][described] = now
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n")


def gaps(prefixes: list[str]) -> None:
    items = inventory()
    for item in open_items(items, source.written(HELP)):
        if not prefixes or any(item.startswith(each) for each in prefixes):
            print(f"{item}\t{items[item]}" if items[item] else item)


def sync() -> None:
    still = set(open_items(inventory(), source.written(HELP)))
    left = sorted(listed(UNCOVERED) & still)
    if left:
        UNCOVERED.write_text("\n".join(left) + "\n")
    else:
        UNCOVERED.unlink(missing_ok=True)


def main() -> None:
    command, *rest = sys.argv[1:] or ["check"]
    if command == "check":
        problems = check()
        for problem in problems:
            print(problem, file=sys.stderr)
        if problems:
            sys.exit(f"help: {len(problems)} to put right")
    elif command == "seen" and rest:
        seen(rest)
    elif command == "gaps":
        gaps(rest)
    elif command == "sync":
        sync()
    else:
        sys.exit(__doc__)


main()
