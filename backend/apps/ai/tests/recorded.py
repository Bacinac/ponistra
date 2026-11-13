from collections.abc import Callable

from anthropic.types.beta import BetaMessage


def message(
    stop: str,
    *content: dict,
    details: dict | None = None,
    model: str = "claude-sonnet-5-5",
    usage: dict | None = None,
) -> BetaMessage:
    return BetaMessage.model_validate(
        {
            "id": "msg",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": list(content),
            "stop_reason": stop,
            "stop_details": details,
            "stop_sequence": None,
            "usage": usage or {"input_tokens": 1, "output_tokens": 1},
        }
    )


def used(id: str, name: str, input: dict) -> dict:
    return {"type": "tool_use", "id": id, "name": name, "input": input}


def said(text: str) -> dict:
    return {"type": "text", "text": text}


class Recorded:
    """Answers each request with the next of the messages recorded, or with what the next
    callable gives, or raises it, keeping what each request asked."""

    def __init__(self, *answers: BetaMessage | Exception | Callable[[], BetaMessage]):
        self.answers = list(answers)
        self.asked: list[dict] = []

    def __call__(self, request: dict) -> BetaMessage:
        self.asked.append({**request, "messages": list(request["messages"])})
        answer = self.answers.pop(0)
        if callable(answer):
            answer = answer()
        if isinstance(answer, Exception):
            raise answer
        return answer
