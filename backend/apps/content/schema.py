"""The document's schema, from the file the editor builds its own from (schema/schema.json):
which node may stand in which and in what order, which marks text takes, and what each
attribute holds: its default, which it may always keep, and the JSON Schema any other value
must meet."""

import json
import re
from collections.abc import Callable
from functools import cache

from django.conf import settings
from jsonschema import Draft202012Validator, ValidationError
from jsonschema.exceptions import best_match
from jsonschema.validators import extend
from prosemirror.model import Schema

SPEC = json.loads(settings.SCHEMA.read_text())
DEFS = SPEC["$defs"]


def _enum(name: str) -> tuple:
    return tuple(DEFS[name]["enum"])


LEVELS = _enum("level")
ALIGNMENTS = _enum("align")
LISTS = _enum("list")
NOTES = _enum("note")
TAB_KINDS = _enum("tabKind")
LEADERS = _enum("leader")
FIELDS = _enum("field")
CHART_KINDS = _enum("chartKind")
STACKING = _enum("stacking")
INDENT_STEP = DEFS["indent"]["step"]
INDENT_MAX = DEFS["indent"]["maximum"]
DEEPEST = round(INDENT_MAX / INDENT_STEP)
TAB_MAX = DEFS["tabStop"]["properties"]["at"]["maximum"]
CHART_TITLE_LENGTH = DEFS["chartTitle"]["maxLength"]
TABLE_NAME_LENGTH = DEFS["tableName"]["maxLength"]
CONTENTS_DEPTH = SPEC["nodes"]["contents"]["attrs"]["depth"]["default"]


def attrs_of(spec: dict) -> dict:
    """A node's or a mark's attributes: those of its sets, then its own."""
    merged: dict = {}
    for name in spec.get("attrSets", []):
        merged |= SPEC["attrSets"][name]
    return merged | spec.get("attrs", {})


@cache
def _compiled(pattern: str) -> re.Pattern:
    # JSON Schema's patterns are ECMAScript's, where a closing $ ends the text; Python's $
    # also matches before a newline that ends it.
    return re.compile(re.sub(r"(?<!\\)\$$", r"\\Z", pattern))


def _pattern(validator, pattern, instance, schema):
    if validator.is_type(instance, "string") and not _compiled(pattern).search(instance):
        yield ValidationError(f"{instance!r} does not match {pattern!r}")


Validator = extend(Draft202012Validator, {"pattern": _pattern})


def _inlined(schema):
    # Each reference to the file's $defs is put in its place once: resolved on every check,
    # it costs more than the check itself.
    if isinstance(schema, list):
        return [_inlined(each) for each in schema]
    if not isinstance(schema, dict):
        return schema
    rest = {key: _inlined(value) for key, value in schema.items() if key != "$ref"}
    if "$ref" not in schema:
        return rest
    target = _inlined(DEFS[schema["$ref"].removeprefix("#/$defs/")])
    return {**rest, "allOf": [*rest.get("allOf", []), target]} if rest else target


def validator(schema: dict | bool) -> Draft202012Validator:
    return Validator(_inlined(schema))


Check = Callable[[object], bool]
# What a schema says to its readers alone.
ANNOTATIONS = {"description", "step"}
TYPES: dict[str, Check] = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: (
        (isinstance(value, int) and not isinstance(value, bool))
        or (isinstance(value, float) and value.is_integer())
    ),
    "number": lambda value: isinstance(value, int | float) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
}


def _number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _equal(one: object, two: object) -> bool:
    """Equality as JSON Schema's enum and const see it: true is not 1, nor false 0."""
    if isinstance(one, str) or isinstance(two, str):
        return one == two
    if isinstance(one, dict) and isinstance(two, dict):
        return one.keys() == two.keys() and all(_equal(one[key], two[key]) for key in one)
    if isinstance(one, list) and isinstance(two, list):
        return len(one) == len(two) and all(map(_equal, one, two, strict=True))
    if isinstance(one, bool) or isinstance(two, bool):
        return type(one) is type(two) and one == two
    return one == two


def _keyword(key: str, given, schema: dict) -> Check:
    match key:
        case "type":
            kinds = [TYPES[each] for each in ([given] if isinstance(given, str) else given)]
            return lambda value: any(kind(value) for kind in kinds)
        case "properties":
            inner = {name: _check(each) for name, each in given.items()}
            return lambda value: (
                not isinstance(value, dict)
                or all(inner[name](value[name]) for name in inner.keys() & value.keys())
            )
        case "additionalProperties":
            known = set(schema.get("properties", ()))
            rest = _check(given)
            return lambda value: (
                not isinstance(value, dict)
                or all(rest(value[name]) for name in value.keys() - known)
            )
        case "required":
            return lambda value: not isinstance(value, dict) or all(name in value for name in given)
        case "minProperties":
            return lambda value: not isinstance(value, dict) or len(value) >= given
        case "items":
            each = _check(given)
            return lambda value: not isinstance(value, list) or all(map(each, value))
        case "minItems":
            return lambda value: not isinstance(value, list) or len(value) >= given
        case "maxItems":
            return lambda value: not isinstance(value, list) or len(value) <= given
        case "enum":
            return lambda value: any(_equal(value, each) for each in given)
        case "const":
            return lambda value: _equal(value, given)
        case "minimum":
            return lambda value: not _number(value) or value >= given
        case "maximum":
            return lambda value: not _number(value) or value <= given
        case "exclusiveMinimum":
            return lambda value: not _number(value) or value > given
        case "minLength":
            return lambda value: not isinstance(value, str) or len(value) >= given
        case "maxLength":
            return lambda value: not isinstance(value, str) or len(value) <= given
        case "pattern":
            found = _compiled(given).search
            return lambda value: not isinstance(value, str) or found(value) is not None
        case "anyOf":
            options = [_check(each) for each in given]
            return lambda value: any(option(value) for option in options)
        case "allOf":
            parts = [_check(each) for each in given]
            return lambda value: all(part(value) for part in parts)
    raise NotImplementedError(f"the schema's {key} is not checked")


def _check(schema: dict | bool) -> Check:
    """The schema, its references put in place, as one function of the value; jsonschema
    stays for what a value lacks, its check for each cell of a large table being too slow."""
    if isinstance(schema, bool):
        return lambda value: schema
    checks = [
        _keyword(key, given, schema) for key, given in schema.items() if key not in ANNOTATIONS
    ]
    if len(checks) == 1:
        return checks[0]
    return lambda value: all(check(value) for check in checks)


def checker(schema: dict | bool) -> Check:
    return _check(_inlined(schema))


@cache
def _defaults(node: str) -> dict:
    return {
        name: each["default"]
        for name, each in attrs_of(SPEC["nodes"][node]).items()
        if "default" in each
    }


def at_default(node: str, name: str, value: object) -> bool:
    """Whether the node's attribute holds its default, as an editor writes every attribute."""
    defaults = _defaults(node)
    # 0 equals False and 1 True in Python, so the default is told by its type as well.
    return name in defaults and type(value) is type(defaults[name]) and value == defaults[name]


@cache
def _defined(name: str) -> Check:
    return checker(DEFS[name])


def holds(name: str, value: object) -> bool:
    """Whether the value meets the definition of that name, as a table's name."""
    return _defined(name)(value)


def _attribute(spec: dict) -> dict:
    holding = checker(spec["schema"])
    checking = validator(spec["schema"])
    has_default = "default" in spec
    default = spec.get("default")

    def validate(value: object) -> None:
        # 0 equals False and 1 True in Python, so the default is told by its type as well.
        if has_default and type(value) is type(default) and value == default:
            return
        if holding(value):
            return
        error = best_match(checking.iter_errors(value))
        if error is not None:
            raise ValueError(error.message)

    return {"default": default, "validate": validate} if has_default else {"validate": validate}


def _type(spec: dict) -> dict:
    own = {key: value for key, value in spec.items() if key not in ("attrs", "attrSets")}
    attrs = {name: _attribute(each) for name, each in attrs_of(spec).items()}
    return {**own, "attrs": attrs} if attrs else own


@cache
def prosemirror() -> Schema:
    """The schema as ProseMirror's, so a node is checked against it as the editor checks it:
    its content, its marks and its attributes' values."""
    return Schema(
        {
            "nodes": {name: _type(spec) for name, spec in SPEC["nodes"].items()},
            "marks": {name: _type(spec) for name, spec in SPEC["marks"].items()},
        }
    )
