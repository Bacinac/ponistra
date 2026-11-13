"""The actions (D14): named intents on a target, each defined here once, with the JSON Schema
of its parameters, the code that plans its operations, how its result is reviewed and the
model that carries it out, if one does. The frontend lists them as commands, labelled in its
own i18n."""

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from typing import Literal

from jsonschema import Draft202012Validator
from pycrdt import Doc

from apps.ai.model import Prompt
from apps.content import schema
from apps.content.operations import IDS
from apps.content.sheets import Sheets
from apps.documents.models import Node, Tab
from apps.mail import acting
from apps.mail.models import Role as MailRole
from apps.versions import compared

from . import agent, gathering, language, review, tables, translation

ID = {"$ref": "#/$defs/id"}
POINT = {"$ref": "#/$defs/point"}
UUID = {
    "type": "string",
    "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
}
TARGETS = {
    "table": {
        "type": "object",
        "properties": {"table": ID},
        "required": ["table"],
        "additionalProperties": False,
    },
    "column": {
        "type": "object",
        "properties": {"table": ID, "col": ID},
        "required": ["table", "col"],
        "additionalProperties": False,
    },
    "document": {"type": "object", "additionalProperties": False},
    "text": {
        "type": "object",
        "properties": {"blocks": IDS},
        "additionalProperties": False,
    },
    "proposals": {
        "type": "object",
        "properties": {"ids": IDS},
        "required": ["ids"],
        "additionalProperties": False,
    },
    "range": {
        "type": "object",
        "properties": {"table": ID, "from": POINT, "to": POINT},
        "required": ["table"],
        "dependentRequired": {"from": ["to"], "to": ["from"]},
        "additionalProperties": False,
    },
    "nodes": {
        "type": "object",
        "properties": {
            "nodes": {
                "type": "array",
                "items": UUID,
                "minItems": 1,
                "maxItems": 500,
                "uniqueItems": True,
            }
        },
        "required": ["nodes"],
        "additionalProperties": False,
    },
    "messages": {
        "type": "object",
        "properties": {
            "messages": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 1,
                "maxItems": 500,
                "uniqueItems": True,
            }
        },
        "required": ["messages"],
        "additionalProperties": False,
    },
}
# The targets inside a tab, which the editor and an outside agent run actions on.
TAB_TARGETS = {"table", "column", "document", "text", "proposals", "range"}
MAIL_TO = {
    "anyOf": [
        {"type": "integer"},
        {"enum": [role for role in MailRole.values if role != MailRole.SNOOZED]},
    ]
}
AT = {"type": "string"}
BY = {"enum": ["address", "domain"]}

Plan = (
    Callable[[Tab, dict, dict], list | Callable[[Doc, Sheets], list] | Prompt]
    | Callable[[str, list[str], str], Prompt]
    | Callable[[str, str, str], Prompt]
    | Callable[[Tab, dict, dict, object], list | Prompt]
    | Callable[[acting.Acting, object, dict], int | Prompt]
)


def _none() -> dict:
    return {"type": "object", "additionalProperties": False}


def _given(**properties) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


@dataclass(frozen=True)
class Action:
    """An action: its target's kind, the code that plans its operations for a tab, a target
    and parameters, as a list or as what builds it from the tab's state in its room, and the
    JSON Schema of its parameters. What its run writes is applied at once, or, reviewed as
    "propose", written and taken out as proposals under the user who runs it. An action with
    a model plans what the model is asked, and the model writes in the background. One on
    documents plans what the model is asked of each, from what it reads of it, the
    columns and the locale of the document it writes into; one translating a PDF file, of each
    of its pages, from its text, how the page before it ends and the language chosen. One that
    reads a document or a file the user names, or the earlier turns of the user's conversation,
    is given the user, whose right to read them it checks, and one with an author proposes
    under the name it gives for its parameters."""

    id: str
    target: str
    plan: Plan
    parameters: dict = field(default_factory=_none)
    review: Literal["apply", "propose"] = "apply"
    model: str | None = None
    reads: bool = False
    author: Callable[[dict], str] | None = None

    def listed(self) -> dict:
        return {
            "id": self.id,
            "target": self.target,
            "parameters": self.parameters,
            "review": self.review,
            "model": self.model,
        }


ACTIONS = {
    action.id: action
    for action in [
        Action("table.totals", "table", tables.totals),
        Action(
            "table.total",
            "column",
            tables.total,
            {
                "type": "object",
                "properties": {"function": {"enum": list(tables.FUNCTIONS)}},
                "required": ["function"],
                "additionalProperties": False,
            },
        ),
        Action(
            "table.calculate",
            "column",
            tables.calculate,
            {
                "type": "object",
                "properties": {
                    "operation": {"enum": list(tables.OPERATIONS)},
                    "columns": {"type": "array", "items": ID, "minItems": 2},
                },
                "required": ["operation", "columns"],
                "additionalProperties": False,
            },
        ),
        Action("table.clean", "table", tables.clean),
        Action("table.group", "column", tables.group),
        Action("table.chart", "range", tables.chart),
        Action(
            "text.summarise",
            "text",
            language.summarise,
            review="propose",
            model="claude-sonnet-5-5",
        ),
        Action(
            "text.rewrite",
            "text",
            language.rewrite,
            {
                "type": "object",
                "properties": {"way": {"enum": list(language.WAYS)}},
                "required": ["way"],
                "additionalProperties": False,
            },
            review="propose",
            model="claude-opus-5-5",
        ),
        Action("text.extract", "text", language.extract, review="propose", model="claude-opus-5-5"),
        Action(
            "document.translate",
            "document",
            language.translate,
            {
                "type": "object",
                "properties": {"language": {"enum": list(Node.Locale.values)}},
                "required": ["language"],
                "additionalProperties": False,
            },
            model="claude-opus-5-5",
        ),
        Action(
            "document.compare",
            "document",
            language.compare,
            {
                "type": "object",
                "properties": {"version": UUID},
                "required": ["version"],
                "additionalProperties": False,
            },
            review="propose",
            model="claude-sonnet-5-5",
        ),
        Action(
            "file.compare",
            "document",
            compared.plan,
            {
                "type": "object",
                "properties": {"file": UUID},
                "required": ["file"],
                "additionalProperties": False,
            },
            review="propose",
            reads=True,
            author=compared.author,
        ),
        Action(
            "text.ask",
            "text",
            agent.ask,
            {
                "type": "object",
                "properties": {
                    "request": {"type": "string", "minLength": 1, "maxLength": 4000},
                    "thread": {
                        "description": "The conversation the request continues, by an id the "
                        "caller makes for its first turn.",
                        "type": "string",
                        "pattern": "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                    },
                },
                "required": ["request"],
                "additionalProperties": False,
            },
            review="propose",
            model="claude-opus-5-5",
            reads=True,
        ),
        Action(
            "table.analyse",
            "table",
            agent.analyse,
            {
                "type": "object",
                "properties": {
                    "title": {
                        "description": "What the new tab is called before the tab's own title.",
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 100,
                    }
                },
                "required": ["title"],
                "additionalProperties": False,
            },
            model="claude-opus-5-5",
        ),
        Action(
            "nodes.extract",
            "nodes",
            gathering.extract,
            {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "columns": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1, "maxLength": 100},
                        "minItems": 1,
                        "maxItems": 30,
                        "uniqueItems": True,
                    },
                },
                "required": ["title"],
                "additionalProperties": False,
            },
            model="claude-sonnet-5-5",
        ),
        Action(
            translation.ACTION,
            "nodes",
            translation.plan,
            {
                "type": "object",
                "properties": {"language": {"enum": list(Node.Locale.values)}},
                "required": ["language"],
                "additionalProperties": False,
            },
            model="claude-sonnet-5-5",
        ),
        Action("mail.seen", "messages", acting.seen),
        Action("mail.unseen", "messages", acting.unseen),
        Action("mail.flagged", "messages", acting.flagged),
        Action("mail.unflagged", "messages", acting.unflagged),
        Action("mail.move", "messages", acting.move, _given(to=MAIL_TO)),
        Action("mail.snooze", "messages", acting.snooze, _given(at=AT)),
        Action("mail.unsnooze", "messages", acting.unsnooze),
        Action("mail.await", "messages", acting.await_, _given(at=AT)),
        Action("mail.unawait", "messages", acting.unawait),
        Action("mail.delete", "messages", acting.delete),
        Action("mail.block", "messages", acting.block, _given(by=BY)),
        Action("mail.always", "messages", acting.always, _given(to=MAIL_TO, by=BY)),
        Action(
            acting.TRIAGE, "messages", acting.triage, review="propose", model=acting.TRIAGE_MODEL
        ),
        Action("proposal.accept", "proposals", review.accept),
        Action("proposal.reject", "proposals", review.reject),
        Action("document.accept", "document", review.accept),
        Action("document.reject", "document", review.reject),
    ]
}


@cache
def _checking(action: str, name: str) -> Draft202012Validator:
    found = ACTIONS[action]
    return schema.validator(found.parameters if name == "parameters" else TARGETS[found.target])


def unfit(action: Action, parameters: object) -> str | None:
    """Why the parameters do not fit the action, by the one it names wrongly or leaves out where
    there is one, as an API refuses it."""
    error = next(_checking(action.id, "parameters").iter_errors(parameters), None)
    if error is None:
        return None
    named = error.path[0] if error.path else None
    if error.validator == "required" and isinstance(parameters, dict):
        named = next(name for name in error.validator_value if name not in parameters)
    return f"invalid_{named}" if isinstance(named, str) else "invalid_parameters"


def invalid(action: Action, target: object, parameters: object) -> str | None:
    """Why the target or the parameters do not fit the action, if they do not."""
    for name, given in [("target", target), ("parameters", parameters)]:
        if not _checking(action.id, name).is_valid(given):
            return f"invalid_{name}"
    return None
