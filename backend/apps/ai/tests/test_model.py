import json
from decimal import Decimal
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from apps.ai import model
from apps.ai.model import Among, Choice, Failed, Prompt, Spent, converse, spent, tool
from apps.content.sheets import Refused

from .recorded import Recorded, message, said, used

AT = {"after": "a"}
BLOCKS = [{"type": "paragraph", "content": [{"type": "text", "text": "Ukratko."}]}]
PROMPT = Prompt("Sažmi.", "[a] paragraph: Najam stana", {"insert": {"at": AT}})


def recorded(monkeypatch, *answers) -> Recorded:
    found = Recorded(*answers)
    monkeypatch.setattr(model, "answer", found)
    return found


def test_an_operation_is_a_tool_of_the_fields_the_action_leaves_to_the_model():
    found = tool("insert", {"at": AT})
    assert found["name"] == "insert" and found["description"]
    schema = found["input_schema"]
    assert set(schema["properties"]) == {"blocks"} and schema["required"] == ["blocks"]
    assert "$ref" not in json.dumps(schema)
    style = tool("style", {})["input_schema"]
    assert set(style["properties"]) == {"style", "font", "size"} and style["required"] == ["style"]
    marked = tool("mark", {})["input_schema"]
    assert "allOf" not in marked
    assert (
        '"size":{"pt":{"type":"number","minimum":1,"maximum":400}}'
        in (marked["properties"]["attrs"]["description"])
    )


def test_the_model_s_calls_are_carried_out_with_the_fields_the_action_fixes(monkeypatch):
    found = recorded(
        monkeypatch,
        message("tool_use", said("Pišem."), used("u1", "insert", {"blocks": BLOCKS})),
        message("end_turn", said("Gotovo.")),
    )
    calls = []

    def call(operation: dict) -> list[dict]:
        calls.append(operation)
        return [{"block": "s1"}]

    spending = []
    assert converse("claude-sonnet-5-5", PROMPT, call, lambda: False, spending.append) == "Gotovo."
    assert calls == [{"blocks": BLOCKS, "at": AT, "op": "insert"}]
    assert spending == 2 * [Spent("claude-sonnet-5-5", 1, 1, 0, 0, Decimal("0.000012"))]
    first, second = found.asked
    assert first["model"] == "claude-sonnet-5-5" and first["fallbacks"] == "default"
    assert first["betas"] == [model.FALLBACK]
    assert first["output_config"] == {"effort": "medium"}
    assert first["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert first["messages"] == [{"role": "user", "content": PROMPT.content}]
    (result,) = second["messages"][-1]["content"]
    assert result == {
        "type": "tool_result",
        "tool_use_id": "u1",
        "content": json.dumps([{"block": "s1"}]),
    }


def test_an_answer_costs_its_tokens_at_the_price_of_each_model_that_gave_them(caplog):
    tokens = {"cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    cached = message(
        "end_turn",
        model="claude-opus-5-5",
        usage={
            "input_tokens": 1000,
            "output_tokens": 200,
            "cache_read_input_tokens": 10000,
            "cache_creation_input_tokens": 2000,
        },
    )
    assert spent("claude-opus-5-5", cached) == Spent(
        "claude-opus-5-5", 1000, 200, 10000, 2000, Decimal("0.02")
    )
    short = {"input_tokens": 1000, "output_tokens": 1000}
    long = {"input_tokens": 90000, "output_tokens": 1000, "cache_read_input_tokens": 20000}
    assert spent(
        "claude-haiku-5-5", message("end_turn", model="claude-haiku-5-5", usage=short)
    ).cost == Decimal("0.0006")
    assert spent(
        "claude-haiku-5-5", message("end_turn", model="claude-haiku-5-5", usage=long)
    ).cost == Decimal("0.0485")
    rescued = message(
        "end_turn",
        model="claude-opus-4-8",
        usage={
            "input_tokens": 500,
            "output_tokens": 100,
            "iterations": [
                {
                    "type": "message",
                    "model": "claude-opus-5-5",
                    "input_tokens": 500,
                    "output_tokens": 0,
                    **tokens,
                },
                {
                    "type": "fallback_message",
                    "model": "claude-opus-4-8",
                    "input_tokens": 500,
                    "output_tokens": 100,
                    **tokens,
                },
            ],
        },
    )
    assert spent("claude-opus-5-5", rescued) == Spent(
        "claude-opus-4-8", 1000, 100, 0, 0, Decimal("0.007")
    )
    assert spent("claude-opus-9", message("end_turn", model="claude-opus-9")).cost is None
    assert "no price for the model claude-opus-9" in caplog.text


def test_a_call_the_document_refuses_goes_back_to_the_model_to_put_right(monkeypatch):
    found = recorded(
        monkeypatch,
        message(
            "tool_use",
            used("u1", "insert", {"blocks": [{"type": "nothing"}]}),
            used("u2", "delete", {"ids": ["a"]}),
        ),
        message("end_turn", said("Gotovo.")),
    )

    def call(operation: dict) -> list[dict]:
        raise Refused("schema", "no node nothing")

    converse("claude-haiku-5-5", PROMPT, call, lambda: False, lambda spent: None)
    assert "fallbacks" not in found.asked[0] and "betas" not in found.asked[0]
    refused, unknown = found.asked[1]["messages"][-1]["content"]
    assert refused["is_error"] and refused["content"] == "schema: no node nothing"
    assert unknown["is_error"] and unknown["content"] == "unknown tool delete"


def test_a_field_the_action_bounds_is_the_model_s_to_fill_among_the_values_given(monkeypatch):
    prompt = Prompt("Prepiši.", PROMPT.content, {"rewrite": {"block": Among(("a", "b"))}})
    schema = tool("rewrite", prompt.tools["rewrite"])["input_schema"]
    assert schema["properties"]["block"] == {"enum": ["a", "b"]}
    assert schema["required"] == ["block", "text"]
    found = recorded(
        monkeypatch,
        message(
            "tool_use",
            used("u1", "rewrite", {"block": "z", "text": "Drugo"}),
            used("u2", "rewrite", {"block": "b", "text": "Novo"}),
        ),
        message("end_turn", said("Gotovo.")),
    )
    calls = []
    converse(
        "claude-opus-5-5",
        prompt,
        lambda operation: calls.append(operation) or [],
        lambda: False,
        lambda spent: None,
    )
    assert calls == [{"block": "b", "text": "Novo", "op": "rewrite"}]
    bounded, done = found.asked[1]["messages"][-1]["content"]
    assert bounded["is_error"] and bounded["content"] == "block is one of a, b"
    assert done["content"] == "done"


def test_a_choice_is_answered_as_its_schema_says_and_its_answer_ends_the_conversation(
    monkeypatch,
):
    level = {"type": "object", "properties": {"level": {"enum": [1, 2]}}, "required": ["level"]}
    choice = Choice("Gives the level.", level)
    assert tool("level", choice) == {
        "name": "level",
        "description": "Gives the level.",
        "input_schema": level,
    }
    found = recorded(
        monkeypatch,
        message("tool_use", used("u1", "level", {"level": 3})),
        message("tool_use", used("u2", "level", {"level": 2})),
    )
    calls = []
    prompt = Prompt("Choose.", "Uvod", {"level": choice})
    converse(
        "claude-haiku-5-5",
        prompt,
        lambda answer: calls.append(answer) or [],
        lambda: False,
        lambda spent: None,
    )
    assert calls == [{"level": 2, "op": "level"}]
    (result,) = found.asked[1]["messages"][-1]["content"]
    assert result["is_error"] and "3 is not one of [1, 2]" in result["content"]
    assert "fallbacks" not in found.asked[0]


def test_a_run_stops_short_where_the_model_declines_runs_out_of_room_or_of_steps(monkeypatch):
    declined = message("refusal", details={"type": "refusal", "category": "cyber"})
    for answer, code in [(declined, "refused"), (message("max_tokens"), "too_long")]:
        recorded(monkeypatch, answer)
        with pytest.raises(Failed) as failed:
            converse(
                "claude-sonnet-5-5", PROMPT, lambda operation: [], lambda: False, lambda spent: None
            )
        assert failed.value.code == code
    monkeypatch.setattr(model, "STEPS", 2)
    again = message("tool_use", used("u1", "insert", {"blocks": BLOCKS}))
    recorded(monkeypatch, again, again)
    with pytest.raises(Failed) as failed:
        converse(
            "claude-sonnet-5-5", PROMPT, lambda operation: [], lambda: False, lambda spent: None
        )
    assert failed.value.code == "too_many_steps"


def test_a_stopped_run_asks_nothing_more_and_calls_nothing_more(monkeypatch):
    found = recorded(monkeypatch)
    converse("claude-sonnet-5-5", PROMPT, lambda operation: [], lambda: True, lambda spent: None)
    assert found.asked == []
    asked = iter([False, True])
    calls = []
    recorded(
        monkeypatch,
        message(
            "tool_use",
            used("u1", "insert", {"blocks": BLOCKS}),
            used("u2", "insert", {"blocks": BLOCKS}),
        ),
    )
    converse("claude-sonnet-5-5", PROMPT, calls.append, lambda: next(asked), lambda spent: None)
    assert calls == []


def test_the_api_s_errors_are_named_for_the_editor(monkeypatch):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    for error, code in [
        (
            anthropic.AuthenticationError(
                "no", response=httpx2.Response(401, request=request), body=None
            ),
            "key_refused",
        ),
        (
            anthropic.RateLimitError(
                "slow", response=httpx2.Response(429, request=request), body=None
            ),
            "rate_limited",
        ),
        (
            anthropic.InternalServerError(
                "down", response=httpx2.Response(500, request=request), body=None
            ),
            "api",
        ),
        (anthropic.APIConnectionError(request=request), "ai_unreachable"),
    ]:

        def stream(error=error, **request):
            raise error

        messages = SimpleNamespace(stream=stream)
        monkeypatch.setattr(
            model,
            "client",
            lambda messages=messages: SimpleNamespace(beta=SimpleNamespace(messages=messages)),
        )
        with pytest.raises(Failed) as failed:
            model.answer({"model": "claude-sonnet-5-5", "messages": []})
        assert failed.value.code == code
