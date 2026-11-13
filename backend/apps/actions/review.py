"""Proposals accepted or rejected (A3): those the target names, or all of the tab's."""

from apps.documents.models import Tab


def accept(tab: Tab, target: dict, parameters: dict) -> list:
    return [{"op": "accept", **target}]


def reject(tab: Tab, target: dict, parameters: dict) -> list:
    return [{"op": "reject", **target}]
