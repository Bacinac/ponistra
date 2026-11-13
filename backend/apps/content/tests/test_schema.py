import pytest
from jsonschema import Draft202012Validator
from prosemirror.model import Node

from apps.content import schema


def attributes():
    for kind in ("nodes", "marks"):
        for name, spec in schema.SPEC[kind].items():
            for attr, each in schema.attrs_of(spec).items():
                yield f"{name}.{attr}", each


@pytest.mark.parametrize(("name", "attr"), list(attributes()))
def test_every_attribute_has_a_valid_schema_its_default_meets(name, attr):
    Draft202012Validator.check_schema(attr["schema"])
    if attr.get("default") is not None:
        assert schema.validator(attr["schema"]).is_valid(attr["default"]), name


def paragraph(attrs=None, content=None):
    block = {"type": "paragraph", "attrs": attrs or {}}
    return {"type": "doc", "content": [{**block, **({"content": content} if content else {})}]}


def test_a_document_is_checked_as_the_editor_checks_it():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"id": "h1", "level": 2},
                "content": [{"type": "text", "text": "Ponuda"}],
            },
            {
                "type": "paragraph",
                "attrs": {
                    "id": "p1",
                    "align": "justify",
                    "indent": 2.5,
                    "tabs": [{"at": 4, "kind": "decimal", "leader": "dot"}],
                    "list": "number",
                },
                "content": [
                    {
                        "type": "text",
                        "text": "Cijena",
                        "marks": [{"type": "strong"}, {"type": "size", "attrs": {"pt": 11}}],
                    },
                    {
                        "type": "footnote",
                        "attrs": {"id": "n1", "kind": "end"},
                        "content": [{"type": "text", "text": "bez PDV-a"}],
                    },
                ],
            },
            {
                "type": "table",
                "attrs": {"id": "t1", "name": "Cijene", "designs": [{"rules": "excel"}]},
                "content": [
                    {
                        "type": "cell",
                        "attrs": {"row": "r1", "col": "c1"},
                        "content": [{"type": "paragraph"}],
                    }
                ],
            },
            {
                "type": "chart",
                "attrs": {
                    "id": "g1",
                    "kind": "pie",
                    "range": {"table": "t1", "from": {"row": "r1", "col": "c1"}},
                },
            },
        ],
    }
    Node.from_json(schema.prosemirror(), doc).check()


@pytest.mark.parametrize(
    "doc",
    [
        paragraph({"align": "middle"}),
        paragraph({"indent": 11}),
        paragraph({"tabs": [{"at": 2, "kind": "bar"}]}),
        paragraph({"restart": 0}),
        paragraph({"style": "Heading 1"}),
        paragraph({"id": "a\n"}),
        paragraph(
            content=[{"type": "text", "text": "x", "marks": [{"type": "size", "attrs": {"pt": 0}}]}]
        ),
        {"type": "doc", "content": [{"type": "heading", "attrs": {"level": 5}}]},
        {"type": "doc", "content": [{"type": "table", "attrs": {"grid": {"rows": []}}}]},
        {"type": "doc", "content": [{"type": "cell", "content": [{"type": "paragraph"}]}]},
        {"type": "doc", "content": []},
    ],
)
def test_what_the_schema_does_not_allow_is_refused(doc):
    with pytest.raises(ValueError):
        Node.from_json(schema.prosemirror(), doc).check()


def test_a_tables_name_is_one_a_sheet_could_have():
    assert schema.holds("tableName", "Cijene 2026")
    assert schema.holds("tableName", "x" * 31)
    for refused in ("'Cijene", "Cijene'", "a:b", "a/b", "ab\n", "x" * 32):
        assert not schema.holds("tableName", refused)


PLAIN = [None, True, False, 0, 1, -1, 1.0, 1.5, -0.5, 1e9, "", "a", "A1", "#FF0000", "x" * 300]
PLAIN += [[], [1], ["a"], [None], {}, {"a": 1}, {"text": "a"}]


def samples(spec, depth=0) -> list:
    """Values at and around what the schema allows: its enums and constants, its bounds and
    either side of them, objects of its properties with and without what they require, and
    lists of its items."""
    if not isinstance(spec, dict) or depth > 3:
        return []
    found = [*spec.get("enum", []), *([spec["const"]] if "const" in spec else [])]
    for key in ("minimum", "maximum"):
        if key in spec:
            found += [spec[key] - 1, spec[key] - 0.5, spec[key], spec[key] + 0.5, spec[key] + 1]
    for key in ("minLength", "maxLength"):
        if key in spec:
            found += ["x" * max(spec[key] + step, 0) for step in (-1, 0, 1)]
    for each in [*spec.get("anyOf", []), *spec.get("allOf", [])]:
        found += samples(each, depth + 1)
    if "items" in spec:
        inner = samples(spec["items"], depth + 1)[:6]
        found += [[each] for each in inner] + [inner]
    if properties := spec.get("properties"):
        least = {
            name: next(iter(samples(properties[name], depth + 1) + ["a"]))
            for name in spec.get("required", [])
        }
        found += [least, {**least, "unknown": 1}]
        for name, inner in properties.items():
            found += [{**least, name: each} for each in samples(inner, depth + 1)[:8]]
    return found[:400]


def definitions():
    yield from schema.DEFS.items()
    yield from ((name, attr["schema"]) for name, attr in attributes())


@pytest.mark.parametrize(("name", "spec"), list(definitions()))
def test_the_quick_check_judges_as_jsonschema_does(name, spec):
    inlined = schema._inlined(spec)
    quick, full = schema.checker(spec), schema.validator(spec)
    for value in PLAIN + samples(inlined):
        assert quick(value) == full.is_valid(value), (name, value)
