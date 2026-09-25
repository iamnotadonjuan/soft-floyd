"""Turns a pydantic model into the strict JSON Schema OpenAI's structured
outputs require: every property listed in `required` (optionality is
expressed as a nullable type, never an absent key), `additionalProperties:
false` on every object (including inside `$defs`), and no bare `default`/
`title` noise OpenAI's schema validator rejects. `guardrail.py`'s
hand-written schema is simple enough to write by hand; training session
generation isn't, so this is shared instead of duplicated.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def _tighten(node: Any) -> None:
    if isinstance(node, list):
        for item in node:
            _tighten(item)
        return
    if not isinstance(node, dict):
        return

    node.pop("title", None)
    node.pop("default", None)

    if node.get("type") == "object" or "properties" in node:
        properties = node.get("properties")
        if properties is not None:
            node["required"] = list(properties.keys())
            node["additionalProperties"] = False

    # A pydantic Optional[X] becomes {"anyOf": [{...X}, {"type": "null"}]}.
    # OpenAI's strict mode wants a nullable type, not anyOf-with-null.
    any_of = node.get("anyOf")
    if isinstance(any_of, list) and any(
        isinstance(branch, dict) and branch.get("type") == "null" for branch in any_of
    ):
        rest = [b for b in any_of if not (isinstance(b, dict) and b.get("type") == "null")]
        node.pop("anyOf", None)
        if len(rest) == 1 and "type" in rest[0]:
            node.update(rest[0])
            existing = node.get("type")
            node["type"] = [existing, "null"] if isinstance(existing, str) else existing
        else:
            node["anyOf"] = [*rest, {"type": "null"}]

    for value in node.values():
        _tighten(value)


def to_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """A JSON Schema for `model` usable as OpenAI's `json_schema.schema`
    with `strict: true`. `$defs` are walked too — every nested model
    needs the same tightening, not just the root.
    """
    schema = model.model_json_schema()
    _tighten(schema)
    return schema
