"""The gate's choice of tests (scripts/check.sh), run in the backend's image with the tree at /tree
and the run's folder at /map.

  select.py plan    the tests the change in /map/diff reaches, by the record of what each test
                    ran in the full runs (/map/map.json): plan.env, and the tests in pytest.txt,
                    vitest.txt and e2e.txt
  select.py merge   that record, laid from what a full run left in /map over the one before it
                    (before.json): map.json, and what failed in the run: failed.json
  select.py corpus  the corpus's fingerprint and the ICU it ran on, for a run that passed it whole

The record names the files each test ran and in them the top-level functions and classes it ran
(apps/core/checkmap.py notes them for pytest and the server, e2e/tests/fixtures.ts for the
browser). A change inside one reaches the tests that ran it. A change to a value, or to a function
no test ran under its name (an arrow handed to memo), reaches what uses it, in its file and in the
files importing it, until it meets functions tests ran; a change at the top level of a file, or a
trail that ends without one, reaches every test that ran the file. A key more than half the
browser's tests ran is the shell, and reaches only a few tests of what everyone does (SMOKE).

A change runs what its reach is: the backend's settings or image, every pytest test; the
frontend's image or build, every vitest test; compose, a stack that starts; a route, the tests
that ran its view. Only the schema, colours, fonts and the recording of what tests run, or a file
this does not know, run everything; a migration, every test that ran its app. Excel's corpus
(apps/engine/tests) runs only where its fingerprint, all it runs and the versions it runs on, has
not passed before (.git/ponistra-check/corpus), in hr and en unless the change reaches what tells
the languages apart. The gate's own scripts are tried by running it, and each night in full."""

import ast
import hashlib
import json
import posixpath
import re
import sys
from functools import cache
from importlib.metadata import version
from pathlib import Path

import icu

TREE = Path("/tree")
RUN = Path("/map")

EVERYTHING = re.compile(r"(schema|colors|fonts)/.*|backend/apps/core/checkmap\.py")
ROUTES = "backend/config/urls.py"
BACKEND_SETTINGS = re.compile(r"backend/(manage\.py|config/.*|apps/conftest\.py)")
BACKEND_IMAGE = re.compile(
    r"backend/(Dockerfile|entrypoint\.sh|requirements.*|overrides\.txt|pyproject\.toml)"
)
SERVICES = re.compile(r"(converter|ocr|recorder)/.*")
PRINTER = re.compile(r"printer/.*")
FRONTEND_IMAGE = re.compile(
    r"frontend/(Dockerfile|package(-lock)?\.json|packages\.sh|patches/.*|tsconfig\.json"
    r"|vite\.config\.ts|index\.html|\.dockerignore)"
)
COMPOSE = re.compile(r"compose\.yaml|compose\.override\.yaml|compose\.check\.yml")
EVERY_BROWSER_TEST = re.compile(
    r"e2e/(Dockerfile|package(-lock)?\.json|playwright\.config\.ts|tests/fixtures\.ts)"
    r"|backend/apps/users/management/commands/e2e_session\.py|frontend/Caddyfile"
)
SHELF = re.compile(r"e2e/shelf/.*")
PHONE = "tests/phone.spec.ts"
CORPUS = "apps/engine/tests/"
# What tells the languages apart: a change here runs the corpus in each of them.
EVERY_LANGUAGE = re.compile(r"backend/apps/engine/(parse|formats|numformat|collation)\.py")
PUSHED_LANGUAGES = "hr,en"
VERSIONED = ("Django", "numpy", "openpyxl", "PyICU", "psycopg", "pytest", "pytest-django")
# What the corpus's tests run that does not bear on it: the migrations of apps it reads nothing
# of, run under the first test that takes the database, and the recording of what tests run.
UNBORNE = re.compile(
    r"backend/apps/(?!engine/|content/)[^/]+/migrations/.*|backend/apps/core/checkmap\.py"
)
POSTGRES = re.compile(r"^\s*image:\s*(postgres:\S+)", re.M)
# What everyone does, run after a push in place of every browser test the shell reaches: by spec
# and the start of the test's title.
SMOKE = {
    "tests/navigation.spec.ts": "the day starts at Today",
    "tests/editor.spec.ts": "two windows edit one document",
    "tests/tables.spec.ts": "a formula is written in its cell",
    "tests/mail.spec.ts": "an account is connected through its server settings",
    "tests/import.spec.ts": "an imported workbook is listed as a spreadsheet",
}
SHELL = "@shell"
# What every page loads without a test's coverage naming it: the entry, styles and assets.
SHELL_FILES = re.compile(r"frontend/src/(main\.tsx|.*\.(css|svg|png|ico|txt|js|json))")
STYLES = re.compile(r"frontend/src/.*\.css")
LOOKS = ("tests/theme.spec.ts", "tests/accessibility.spec.ts")
ROUTE = re.compile(r"\s*(?:re_)?path\(.*,\s*([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*(?:,.*)?\),?\s*")
ROUTE_IMPORT = re.compile(r"\s*from\s+(apps(?:\.\w+)+)\s+import\s+(.+)")
UNTESTED = re.compile(
    r"(android|docs|deploy|workspace|help|help-shots|e2e/shots|\.claude)/.*|e2e/shots\.config\.ts|[^/]*\.md|NOTICE|VERSION|\.gitignore"
    r"|\.env\.example|compose\.docker\.yaml|backend/\.dockerignore"
    r"|scripts/(brand\.mjs|gen-revision\.sh|install-hooks\.sh|lock\.sh|release\.sh|git-hooks/.*)"
    r"|scripts/(check\.sh|check-full\.sh|select\.py|help\.py|help\.sh)"
)
STATIC_ONLY = re.compile(r"frontend/\.prettierrc\.json")
MESSAGES = re.compile(r"frontend/src/i18n/(hr|en)\.ts")
LITERAL = re.compile(r"""(['"`])([^'"`\s\\]+)\1""")
TEMPLATE = re.compile(r"`([^`'\"\s$]+)\.\$\{")
ENTRY = re.compile(r"\s*'([^']+)':(.*)")
SPECIFIER = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*)['"](\.{1,2}/[^'"?]+)""")
HUNK = re.compile(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
TRIVIAL = {".py": re.compile(r"\s*(#.*)?"), ".ts": re.compile(r"\s*(//.*|/\*.*|\*.*)?")}
TS_DECLARATION = re.compile(
    r"(?:export\s+(?:default\s+)?)?(?:declare\s+)?(?:async\s+)?(?:abstract\s+)?"
    r"(?P<kind>function\*?|const\s+enum|const|let|var|class|enum|type|interface)\s+(?P<name>[\w$]+)"
)
TS_IMPORT = re.compile(r"import[\s{*]|export\s*(type\s*)?[{*]")
TS_TEST = re.compile(r"test(\.(only|skip|fixme|fail|slow))?\(")


class Record:
    """What one kind of test ran: a file, or `file#name`, to the tests that ran it. With `shell`,
    a key more than half the tests ran reaches SHELL alone."""

    def __init__(self, kept: dict, shell: bool = False):
        self.tests, self.keys = kept["tests"], kept["keys"]
        self.broad = (
            {key for key, found in self.keys.items() if 2 * len(found) > len(self.tests)}
            if shell
            else set()
        )

    def by_test(self) -> dict[str, set[str]]:
        found: dict[str, set[str]] = {test: set() for test in self.tests}
        for key, indexes in self.keys.items():
            for index in indexes:
                found[self.tests[index]].add(key)
        return found

    def __contains__(self, key: str) -> bool:
        return key in self.keys

    def __getitem__(self, key: str) -> set[str]:
        if key in self.broad:
            return {SHELL}
        return {self.tests[index] for index in self.keys[key]}

    def under(self, folder: str) -> set[str]:
        found: set[str] = set()
        for key in self.keys:
            if key.startswith(folder):
                found |= self[key]
        return found


def specs() -> dict[str, str]:
    """The tree's browser specs, by the path a test's id starts with, to their blobs."""
    found = {}
    for line in (RUN / "specs").read_text().splitlines():
        blob, path = line.split()[2], line.split("\t")[1]
        if path.endswith(".spec.ts"):
            found[path.removeprefix("e2e/")] = blob
    return found


def text(path: str) -> str:
    file = TREE / path
    return file.read_text() if file.exists() else ""


def parsed(path: str) -> ast.Module:
    try:
        return ast.parse(text(path), path)
    except SyntaxError as error:
        sys.exit(f"{path}:{error.lineno}: {error.msg}")


@cache
def units(path: str) -> tuple[tuple[int, int, str, str], ...]:
    """The top-level parts of a file: first and last line, kind and name. Kinds: value (a function,
    class or binding, by name), import, type (and docstrings), test (a browser test), other."""
    source = text(path)
    if path.endswith(".py"):
        found = []
        for node in parsed(path).body:
            first = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))])
            name = ""
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                kind, name = "value", node.name
            elif isinstance(node, ast.Import | ast.ImportFrom):
                kind = "import"
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                kind = "type"
            elif isinstance(node, ast.Assign | ast.AnnAssign) and isinstance(
                target := (node.targets[0] if isinstance(node, ast.Assign) else node.target),
                ast.Name,
            ):
                kind, name = "value", target.id
            else:
                kind = "other"
            found.append((first, node.end_lineno, kind, name))
        return tuple(found)
    lines = source.splitlines()
    marks = []
    for number, line in enumerate(lines, 1):
        if not line or line[0] in " \t)]}/*":
            continue
        if TS_IMPORT.match(line):
            marks.append((number, "import", ""))
        elif TS_TEST.match(line):
            marks.append((number, "test", ""))
        elif declaration := TS_DECLARATION.match(line):
            kind = "type" if declaration["kind"] in ("type", "interface") else "value"
            marks.append((number, kind, declaration["name"]))
        else:
            marks.append((number, "other", ""))
    ends = [number - 1 for number, _, _ in marks[1:]] + [len(lines)] * bool(marks)
    return tuple(
        (first, last, kind, name) for (first, kind, name), last in zip(marks, ends, strict=True)
    )


def unit_at(path: str, line: int) -> tuple[int, int, str, str] | None:
    for unit in units(path):
        if unit[0] <= line <= unit[1]:
            return unit
    return None


def hunks(diff: str) -> dict[str, list[tuple[int, int, list[str], list[str]]]]:
    """Each file's changes: where they start and how many lines they take in the new file, the
    lines taken out and those put in."""
    found: dict[str, list] = {}
    old = new = current = None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            old = new = current = None
        elif current is None and line.startswith("--- "):
            old = None if line[4:] == "/dev/null" else line[6:]
        elif current is None and line.startswith("+++ "):
            new = None if line[4:] == "/dev/null" else line[6:]
        elif hunk := HUNK.match(line):
            current = (int(hunk[1]), int(hunk[2] or 1), [], [])
            found.setdefault(new or old, []).append(current)
        elif current is not None and line[:1] == "-":
            current[2].append(line[1:])
        elif current is not None and line[:1] == "+":
            current[3].append(line[1:])
    return found


def touched(path: str, changes) -> tuple[bool, set[str], set[int]]:
    """What a file's changes touch: its top level as a whole, the names of its parts, and the
    first lines of its browser tests."""
    trivial = TRIVIAL[".py" if path.endswith(".py") else ".ts"]
    size = len(text(path).splitlines())
    lines = set()
    for start, count, removed, added in changes:
        lines.update(start + k for k, line in enumerate(added) if not trivial.fullmatch(line))
        if any(not trivial.fullmatch(line) for line in removed):
            lines.update(range(start, start + count) if count else (start, start + 1))
    whole, names, tests = False, set(), set()
    for line in lines:
        unit = unit_at(path, line)
        if unit is None:
            whole = whole or 1 <= line <= size
        elif unit[2] == "value":
            names.add(unit[3])
        elif unit[2] == "test":
            tests.add(unit[0])
        elif unit[2] == "other" or (unit[2] == "import" and path.endswith(".py")):
            whole = True
    return whole, names, tests


@cache
def python_importers() -> dict[str, set[str]]:
    modules = {}
    for folder in ("apps", "config"):
        for file in (TREE / "backend" / folder).rglob("*.py"):
            parts = list(file.relative_to(TREE / "backend").with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            modules[".".join(parts)] = str(file.relative_to(TREE))
    importers: dict[str, set[str]] = {}
    for name, path in modules.items():
        package = name if path.endswith("__init__.py") else name.rpartition(".")[0]
        for node in ast.walk(parsed(path)):
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parts = package.split(".")[: len(package.split(".")) - node.level + 1]
                    base = ".".join([*parts, base] if base else parts)
                targets = [base, *(f"{base}.{alias.name}" for alias in node.names)]
            else:
                continue
            for target in targets:
                if target in modules and modules[target] != path:
                    importers.setdefault(modules[target], set()).add(path)
    return importers


@cache
def script_importers(folder: str) -> dict[str, set[str]]:
    files = {str(file.relative_to(TREE)) for file in (TREE / folder).rglob("*") if file.is_file()}
    importers: dict[str, set[str]] = {}
    for path in files:
        if not path.endswith((".ts", ".tsx")):
            continue
        for specifier in SPECIFIER.findall((TREE / path).read_text()):
            base = posixpath.normpath(posixpath.join(posixpath.dirname(path), specifier))
            ends = ("", ".ts", ".tsx", "/index.ts", "/index.tsx")
            for candidate in (base + end for end in ends):
                if candidate in files:
                    importers.setdefault(candidate, set()).add(path)
                    break
    return importers


def importers_of(path: str) -> dict[str, set[str]]:
    return python_importers() if path.endswith(".py") else script_importers("frontend/src")


def climbed(path: str, found: dict, importers: dict[str, set[str]]) -> set[str]:
    """What `found` holds for the file or, where it holds nothing, for the files importing it."""
    tests: set[str] = set()
    seen, waiting = {path}, [path]
    while waiting:
        file = waiting.pop()
        if file in found:
            tests.update(found[file])
            continue
        above = importers.get(file, set()) - seen
        seen |= above
        waiting.extend(above)
    return tests


def mentions(source: str, name: str) -> bool:
    return re.search(rf"(?<![\w$]){re.escape(name)}(?![\w$])", source) is not None


def users(path: str, name: str) -> list[tuple[str, str | None]]:
    """The parts that name `name` in the file defining it and in the files importing it, by file
    and name; None for top-level code."""
    found = []
    for file in [path, *sorted(importers_of(path).get(path, ()))]:
        lines = text(file).splitlines()
        for first, last, kind, unit in units(file):
            if kind in ("import", "type") or (file == path and unit == name):
                continue
            if mentions("\n".join(lines[first - 1 : last]), name):
                found.append((file, unit if kind == "value" else None))
    return found


def reach(path: str, whole: bool, names: set[str], record: Record) -> set[str] | None:
    """The tests a change reaches; None where it touches nothing they run (comments, types, a
    script's imports)."""
    if whole:
        return climbed(path, record, importers_of(path))
    if not names:
        return None
    tests: set[str] = set()
    seen: set[tuple[str, str]] = set()
    waiting = [(path, name) for name in names]
    while waiting:
        file, name = waiting.pop()
        if (file, name) in seen:
            continue
        seen.add((file, name))
        if f"{file}#{name}" in record:
            tests.update(record[f"{file}#{name}"])
            continue
        for user, unit in users(file, name):
            if unit is None:
                tests.update(climbed(user, record, importers_of(user)))
            else:
                waiting.append((user, unit))
    return tests or climbed(path, record, importers_of(path))


def messages(source: str) -> dict[str, str]:
    found: dict[str, str] = {}
    key = None
    for line in source.splitlines():
        if entry := ENTRY.match(line):
            key = entry[1]
            found[key] = entry[2]
        elif key:
            found[key] += line
    return found


def quoted(sources: dict[str, str]) -> tuple[dict, dict]:
    """Where each text in quotes stands, and each template's text before its first `.${`: by the
    text, the file and its lines."""
    literals: dict[str, dict[str, set[int]]] = {}
    templates: dict[str, dict[str, set[int]]] = {}
    for path, source in sources.items():
        for number, line in enumerate(source.splitlines(), 1):
            for found in LITERAL.finditer(line):
                literals.setdefault(found[2], {}).setdefault(path, set()).add(number)
            for found in TEMPLATE.finditer(line):
                templates.setdefault(found[1], {}).setdefault(path, set()).add(number)
    return literals, templates


def naming(key: str, index: tuple[dict, dict]) -> dict[str, set[int]]:
    """The lines that name a message, by its key or, built from a part, by the part before it."""
    literals, templates = index
    if key in literals:
        return literals[key]
    parts = key.split(".")
    while len(parts) > 1:
        parts.pop()
        if found := templates.get(".".join(parts)):
            return found
    return {}


def smoke() -> set[str]:
    found = set()
    for spec, title in SMOKE.items():
        lines = text(f"e2e/{spec}").splitlines()
        line = next(
            (n for n, line in enumerate(lines, 1) if TS_TEST.match(line) and title in line), None
        )
        if line is None:
            sys.exit(f"select: no test of {spec} starts with {title!r} (SMOKE)")
        found.add(f"{spec}:{line}")
    return found


def routes(changes) -> tuple[bool, dict[str, set[str]]]:
    """What a change to the root's routes touches: anything but its routes and imports as a
    whole, and the views of the routes it adds or takes out by the files defining them."""
    lines = [line for _, _, removed, added in changes for line in [*removed, *added]]
    modules = {}
    for line in [*lines, *text(ROUTES).splitlines()]:
        if found := ROUTE_IMPORT.fullmatch(line):
            for name in found[2].split(","):
                module, _, alias = name.strip().partition(" as ")
                modules[alias or module] = f"{found[1]}.{module}"
    views: dict[str, set[str]] = {}
    for line in lines:
        if TRIVIAL[".py"].fullmatch(line) or ROUTE_IMPORT.fullmatch(line):
            continue
        route = ROUTE.fullmatch(line)
        if route is None or route[1] not in modules:
            return True, {}
        file = f"backend/{modules[route[1]].replace('.', '/')}.py"
        if not (TREE / file).exists():
            return True, {}
        views.setdefault(file, set()).add(route[2])
    return False, views


def every_app_but_the_corpus() -> list[str]:
    return sorted(
        f"apps/{folder.name}/"
        for folder in (TREE / "backend/apps").iterdir()
        if folder.is_dir() and not folder.name.startswith("_") and folder.name != "engine"
    )


def blobs() -> dict[str, str]:
    """The backend's files in the tree checked, to their blobs (/map/blobs, git ls-tree)."""
    found = {}
    for line in (RUN / "blobs").read_text().splitlines():
        meta, path = line.split("\t", 1)
        found[path] = meta.split()[2]
    return found


def fingerprint(record: Record) -> tuple[str, str]:
    """What the corpus runs, as one hash: the engine's files, those the engine imports, those its
    tests ran, the versions of what it runs on and the database's image; and the ICU's version."""
    known = blobs()
    engine = {path for path in known if path.startswith("backend/apps/engine/")}
    imported: dict[str, set[str]] = {}
    for target, by in python_importers().items():
        for path in by:
            imported.setdefault(path, set()).add(target)
    waiting = [path for path in engine if f"/{CORPUS}" not in path]
    files = set(engine)
    while waiting:
        for target in imported.get(waiting.pop(), ()):
            if target not in files:
                files.add(target)
                waiting.append(target)
    corpus = {i for i, test in enumerate(record.tests) if test.startswith(CORPUS)}
    files |= {
        key
        for key, found in record.keys.items()
        if "#" not in key and not UNBORNE.fullmatch(key) and not corpus.isdisjoint(found)
    }
    files.add("backend/apps/conftest.py")
    hashed = hashlib.sha256()
    for path in sorted(files):
        hashed.update(f"{path} {known.get(path, '-')}\n".encode())
    postgres = POSTGRES.search(text("compose.yaml"))
    for part in (
        sys.version,
        icu.ICU_VERSION,
        *(f"{name} {version(name)}" for name in VERSIONED),
        postgres[1] if postgres else "-",
    ):
        hashed.update(f"{part}\n".encode())
    return hashed.hexdigest(), icu.ICU_VERSION


def sealed() -> list[list[str]]:
    """The corpus's runs that passed: fingerprint, ICU's version, languages and when."""
    seals = RUN / "corpus.sealed"
    return [line.split() for line in seals.read_text().splitlines()] if seals.exists() else []


def corpus() -> None:
    print(*fingerprint(Record(json.loads((RUN / "map.json").read_text())["pytest"])))


def plan() -> None:
    changes = hunks((RUN / "diff").read_text())
    changed = (RUN / "changed").read_text().split()
    kept = json.loads((RUN / "map.json").read_text())
    records = {"pytest": Record(kept["pytest"]), "e2e": Record(kept["e2e"], shell=True)}
    now = specs()
    # A test is named by its spec and line as the record's specs had them; in a spec changed
    # since, the line may be another test's.
    moved = {spec for spec, blob in now.items() if kept["specs"].get(spec) != blob}
    pytest: set[str] = set()
    vitest: set[str] = set()
    e2e: set[str] = set()
    edited: set[str] = set()
    every_e2e = backend = frontend = everything = False
    every_pytest = every_vitest = every_corpus = stack = False
    index = None

    for path in changed:
        if EVERYTHING.fullmatch(path):
            everything = True
            continue
        if UNTESTED.fullmatch(path):
            continue
        if path == ROUTES:
            backend = True
            whole, views = routes(changes[path]) if path in changes else (True, {})
            every_pytest = every_pytest or whole
            if whole:
                e2e.add(SHELL)
            for file, names in views.items():
                app = "/".join(file.split("/")[:3]) + "/"
                for kind, chosen in (("pytest", pytest), ("e2e", e2e)):
                    chosen.update(
                        reach(file, False, names, records[kind]) or records[kind].under(app)
                    )
            continue
        if BACKEND_SETTINGS.fullmatch(path) or BACKEND_IMAGE.fullmatch(path):
            backend = every_pytest = True
            every_corpus = every_corpus or bool(BACKEND_IMAGE.fullmatch(path))
            e2e.add(SHELL)
            continue
        if SERVICES.fullmatch(path) or PRINTER.fullmatch(path):
            every_pytest = True
            every_e2e = every_e2e or bool(PRINTER.fullmatch(path))
            e2e.add(SHELL)
            continue
        if FRONTEND_IMAGE.fullmatch(path):
            frontend = every_vitest = True
            e2e.add(SHELL)
            continue
        if COMPOSE.fullmatch(path):
            stack = True
            continue
        if SHELF.fullmatch(path):
            e2e.add(PHONE)
            continue
        exists = (TREE / path).exists()
        if exists and path in changes and path.endswith((".py", ".ts", ".tsx")):
            whole, names, tests = touched(path, changes[path])
        else:
            whole, names, tests = True, set(), set()
        if STATIC_ONLY.fullmatch(path):
            frontend = True
        elif EVERY_BROWSER_TEST.fullmatch(path):
            every_e2e = True
            backend = backend or path.startswith("backend/")
            if path.startswith("frontend/src/"):
                frontend = True
                vitest.add(path.removeprefix("frontend/"))
        elif path.startswith("backend/apps/"):
            backend = True
            inside = path.removeprefix("backend/")
            app = "/".join(path.split("/")[:3]) + "/"
            name = posixpath.basename(path)
            if name == "conftest.py":
                pytest.add(f"{posixpath.dirname(inside)}/")
            elif name.startswith("test_") and name.endswith(".py"):
                if whole or path not in records["pytest"]:
                    pytest.add(inside)
                else:
                    own = {n for n in names if n.startswith(("test", "Test"))}
                    pytest.update(f"{inside}::{n}" for n in own)
                    pytest.update(reach(path, False, names - own, records["pytest"]) or ())
            elif "/migrations/" in path:
                pytest.update(records["pytest"].under(app))
                e2e.update(records["e2e"].under(app))
            elif path.endswith(".py"):
                for kind, chosen in (("pytest", pytest), ("e2e", e2e)):
                    found = reach(path, whole, names, records[kind])
                    if found is not None:
                        # A file no test reaches even through what imports it (an app's urls.py,
                        # read by the root's) is taken as its app's.
                        chosen.update(found or records[kind].under(app))
            elif "/tests/" in path:
                pytest.add(inside.split("/tests/")[0] + "/tests/")
            else:
                pytest.update(records["pytest"].under(app))
                e2e.update(records["e2e"].under(app))
        elif path.startswith("frontend/src/"):
            frontend = True
            vitest.add(path.removeprefix("frontend/"))
            if re.search(r"\.test\.tsx?$", path):
                continue
            if SHELL_FILES.fullmatch(path):
                e2e.add(SHELL)
                if STYLES.fullmatch(path):
                    e2e.update(LOOKS)
            elif MESSAGES.fullmatch(path):
                if index is None:
                    index = quoted(
                        {
                            str(file.relative_to(TREE)): file.read_text()
                            for file in (TREE / "frontend/src").rglob("*.ts*")
                            if "/i18n/" not in str(file)
                            and not re.search(r"\.test\.tsx?$", file.name)
                        }
                    )
                base = RUN / f"{posixpath.basename(path)}.base"
                before = messages(base.read_text()) if base.exists() else {}
                after = messages(text(path))
                for key in {
                    k for k in before.keys() | after.keys() if before.get(k) != after.get(k)
                }:
                    named = naming(key, index)
                    every_e2e = every_e2e or not named
                    for user, lines in named.items():
                        vitest.add(user.removeprefix("frontend/"))
                        parts = [unit_at(user, line) for line in lines]
                        top = any(part is None or part[2] != "value" for part in parts)
                        found = (
                            reach(user, top, {p[3] for p in parts if p}, records["e2e"]) or set()
                        )
                        e2e.update(found)
                        every_e2e = every_e2e or not found
            elif path.endswith((".ts", ".tsx")):
                found = reach(path, whole, names, records["e2e"])
                if found is not None:
                    e2e.update(found)
                    every_e2e = every_e2e or not found
            else:
                every_e2e = True
        elif path.startswith("e2e/tests/") and path.endswith(".spec.ts"):
            if exists:
                spec = path.removeprefix("e2e/")
                edited.update([spec] if whole or names else [f"{spec}:{line}" for line in tests])
        elif path.startswith("e2e/tests/"):
            by_spec = {f"e2e/{spec}": [f"e2e/{spec}"] for spec in now}
            found = climbed(path, by_spec, script_importers("e2e/tests"))
            e2e.update(spec.removeprefix("e2e/") for spec in found)
            every_e2e = every_e2e or not found
        else:
            everything = True

    if everything:
        backend = frontend = every_pytest = every_vitest = every_e2e = every_corpus = True
    corpus = {CORPUS} if every_corpus else {test for test in pytest if test.startswith(CORPUS)}
    pytest -= corpus
    mark = icu = "-"
    languages = PUSHED_LANGUAGES
    if corpus:
        mark, icu = fingerprint(records["pytest"])
        seals = sealed()
        if any(seal[0] == mark for seal in seals):
            corpus = set()
        elif any(EVERY_LANGUAGE.fullmatch(path) for path in changed) or (
            seals and seals[-1][1] != icu
        ):
            languages = "all"

    shell = SHELL in e2e
    e2e.discard(SHELL)
    e2e = {test.split(":")[0] if test.split(":")[0] in moved else test for test in e2e} | edited
    if shell:
        e2e |= smoke()
    whole_specs = {test for test in e2e if ":" not in test}
    write(
        full=everything,
        backend=backend,
        frontend=frontend,
        stack=stack,
        pytest="all" if every_pytest else sorted(pytest),
        vitest="all"
        if every_vitest
        else sorted(file for file in vitest if (TREE / "frontend" / file).exists()),
        e2e="all"
        if every_e2e
        else sorted(
            test
            for test in e2e
            if test.split(":")[0] in now
            and (test in whole_specs or test.split(":")[0] not in whole_specs)
        ),
        corpus="all" if every_corpus and corpus else sorted(corpus),
        languages=languages,
        mark=mark,
        icu=icu,
    )


def write(
    full: bool, backend, frontend, stack, pytest, vitest, e2e, corpus, languages, mark, icu
) -> None:
    """plan.env, and the tests to run in pytest.txt (the corpus's among them), vitest.txt and
    e2e.txt; `all` is every test of its kind, pytest's but the corpus."""

    def amount(tests) -> str:
        return tests if isinstance(tests, str) else str(len(tests))

    listed = {
        "pytest": [
            *(every_app_but_the_corpus() if pytest == "all" else pytest),
            *([CORPUS] if corpus == "all" else corpus),
        ],
        "vitest": () if vitest == "all" else vitest,
        "e2e": () if e2e == "all" else e2e,
    }
    for name, tests in listed.items():
        (RUN / f"{name}.txt").write_text("".join(f"{test}\n" for test in tests))
    (RUN / "plan.env").write_text(
        f"FULL={int(full)}\nBACKEND={int(backend)}\nFRONTEND={int(frontend)}\n"
        f"STACK={int(stack)}\nPYTEST={amount(pytest)}\nVITEST={amount(vitest)}\n"
        f"E2E={amount(e2e)}\nCORPUS={amount(corpus)}\nLANGUAGES={languages}\n"
        f"FINGERPRINT={mark}\nICU={icu}\n"
    )


def browser_outcomes() -> dict[str, list[str]]:
    """The browser tests Playwright's report (playwright.config.ts) tells failed, and those that
    passed only once tried again."""
    found: dict[str, list[str]] = {"e2e": [], "flaky": []}
    report = RUN / "e2e-report.json"
    if not report.exists():
        return found
    told = json.loads(report.read_text())
    root = told["config"]["rootDir"]
    suites = list(told["suites"])
    while suites:
        suite = suites.pop()
        suites.extend(suite.get("suites", []))
        for spec in suite.get("specs", []):
            test = f"{posixpath.relpath(posixpath.join(root, spec['file']), '/e2e')}:{spec['line']}"
            if not spec["ok"]:
                found["e2e"].append(test)
            elif any(run["status"] == "flaky" for run in spec["tests"]):
                found["flaky"].append(test)
    return {kind: sorted(tests) for kind, tests in found.items()}


def still_there(test: str) -> bool:
    """Whether a pytest test of an earlier record is still in the tree, by its file and the
    function or class it starts with."""
    path, _, rest = test.partition("::")
    name = rest.split("::")[0].split("[")[0]
    return (TREE / "backend" / path).exists() and any(
        unit[3] == name for unit in units(f"backend/{path}")
    )


def collected() -> set[str] | None:
    """The pytest tests a full run collected, where its session ran to its end with the tests
    passed or failed (apps/core/checkmap.py); None where it was cut short."""
    status = RUN / "pytest.status"
    if not status.exists() or status.read_text().strip() not in ("0", "1"):
        return None
    found = set()
    for part in RUN.glob("pytest-*.collected"):
        found.update(part.read_text().splitlines())
    return found or None


def merge() -> None:
    """A test that ran replaces its record in the one before, or adds to it where it failed, as it
    ran only part of itself; a test that left no record keeps the old one while the run collected
    it, or, its stage cut short, while it is still in the tree; a browser test only where no test
    of its spec ran (its line may be another's since), under the whole spec where the spec
    changed since."""
    stages = (RUN / "stages").read_text().split()
    ran: dict[str, dict[str, set[str]]] = {"pytest": {}, "e2e": {}}
    for part in RUN.glob("pytest-*.json"):
        for test, files in json.loads(part.read_text()).items():
            ran["pytest"][test] = set(files)
    for part in ("e2e-backend.jsonl", "e2e-frontend.jsonl"):
        if (RUN / part).exists():
            for line in (RUN / part).read_text().splitlines():
                entry = json.loads(line)
                ran["e2e"].setdefault(entry["test"], set()).update(entry["files"])
    for kind, stage in (("pytest", "pytest"), ("e2e", "browser")):
        if not ran[kind] and stage not in stages:
            sys.exit(f"select: the full run's {stage} passed and left no record of what it ran")
    pytest_failed = RUN / "pytest.failed"
    failed = {
        "pytest": pytest_failed.read_text().splitlines() if pytest_failed.exists() else [],
        **browser_outcomes(),
    }
    now = specs()
    present = collected()
    if (RUN / "before.json").exists():
        before = json.loads((RUN / "before.json").read_text())
        ran_specs = {test.split(":")[0] for test in ran["e2e"]}
        for test, files in Record(before["pytest"]).by_test().items():
            if test in ran["pytest"]:
                if test in failed["pytest"]:
                    ran["pytest"][test] |= files
            elif test in present if present is not None else still_there(test):
                ran["pytest"][test] = files
        for test, files in Record(before["e2e"]).by_test().items():
            spec = test.split(":")[0]
            if test in ran["e2e"]:
                if test in failed["e2e"] and before["specs"].get(spec) == now.get(spec):
                    ran["e2e"][test] |= files
            elif spec in now and spec not in ran_specs:
                kept_as = test if before["specs"].get(spec) == now[spec] else spec
                ran["e2e"].setdefault(kept_as, set()).update(files)
    kept: dict = {"specs": now}
    for kind, tests in ran.items():
        names = sorted(tests)
        keys: dict[str, list[int]] = {}
        for index, test in enumerate(names):
            for key in tests[test]:
                keys.setdefault(key, []).append(index)
        kept[kind] = {"tests": names, "keys": keys}
    (RUN / "map.json").write_text(json.dumps(kept, separators=(",", ":")))
    tree = (RUN / "tree").read_text().strip()
    (RUN / "failed.json").write_text(
        json.dumps({"tree": tree, "stages": stages, **failed}, indent=1) + "\n"
    )


if __name__ == "__main__":
    {"plan": plan, "merge": merge, "corpus": corpus}[sys.argv[1]]()
