from __future__ import annotations

import re
from typing import Any


SAFE_DATA_ATTRS = ("testId", "dataTestId", "dataTest", "dataQa", "dataCy")
SHORT_TEXT_LIMIT = 80


def build_target(descriptor: dict[str, Any]) -> dict[str, Any]:
    candidates = build_candidates(descriptor)
    primary = choose_primary(candidates)
    return {
        "primary": primary,
        "candidates": [item for item in candidates if item != primary],
        "fingerprint": fingerprint(descriptor),
    }


def build_candidates(descriptor: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []

    def add(candidate: dict[str, Any]) -> None:
        key = tuple(sorted(candidate.items()))
        if candidate and key not in seen:
            seen.add(key)
            out.append(candidate)

    test_id = first_value(descriptor, SAFE_DATA_ATTRS)
    if test_id:
        add({"kind": "test_id", "value": test_id})

    role = descriptor.get("role") or implied_role(descriptor)
    name = accessible_name(descriptor)
    if role and name:
        add({"kind": "role", "role": role, "name": name})

    for label in descriptor.get("labels") or []:
        add({"kind": "label", "value": label})
    for key, kind in (("placeholder", "placeholder"), ("title", "title"), ("alt", "alt")):
        if descriptor.get(key):
            add({"kind": kind, "value": descriptor[key]})

    text = normalize_space(descriptor.get("text"))
    if text and len(text) <= SHORT_TEXT_LIMIT:
        add({"kind": "text", "value": text})

    for css in stable_css_candidates(descriptor):
        add({"kind": "css", "value": css})

    if descriptor.get("cssPath"):
        add({"kind": "css", "value": descriptor["cssPath"]})
    if descriptor.get("xpath"):
        add({"kind": "xpath", "value": descriptor["xpath"]})
    elif descriptor.get("tag") and text:
        add({"kind": "xpath", "value": f"//{descriptor['tag']}[contains(normalize-space(.), {xpath_literal(text)})]"})

    return out or [{"kind": "css", "value": descriptor.get("cssPath") or "*"}]


def choose_primary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    for candidate in candidates:
        if candidate["kind"] != "xpath":
            return candidate
    return candidates[0]


def fingerprint(descriptor: dict[str, Any]) -> dict[str, Any]:
    keys = ("tag", "role", "text", "id", "name", "type", "placeholder", "title", "alt", "href", "labels", "bbox")
    return {key: descriptor.get(key) for key in keys if descriptor.get(key) not in (None, "", [])}


def first_value(data: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if data.get(key):
            return str(data[key])
    return None


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def accessible_name(descriptor: dict[str, Any]) -> str:
    return normalize_space(
        descriptor.get("ariaLabel")
        or " ".join(descriptor.get("labels") or [])
        or descriptor.get("title")
        or descriptor.get("alt")
        or descriptor.get("text")
        or descriptor.get("value")
    )


def implied_role(descriptor: dict[str, Any]) -> str | None:
    tag = (descriptor.get("tag") or "").lower()
    input_type = (descriptor.get("type") or "").lower()
    if tag == "button" or input_type in {"button", "submit", "reset"}:
        return "button"
    if tag == "a" and descriptor.get("href"):
        return "link"
    if tag in {"input", "textarea"} and input_type not in {"checkbox", "radio"}:
        return "textbox"
    if tag == "select":
        return "combobox"
    if tag == "option":
        return "option"
    return None


def stable_css_candidates(descriptor: dict[str, Any]) -> list[str]:
    tag = descriptor.get("tag") or "*"
    attrs = []
    for key, attr in (
        ("id", "id"),
        ("name", "name"),
        ("type", "type"),
        ("href", "href"),
        ("ariaLabel", "aria-label"),
        ("ariaLabelledby", "aria-labelledby"),
        ("testId", "data-testid"),
        ("dataTest", "data-test"),
        ("dataQa", "data-qa"),
        ("dataCy", "data-cy"),
    ):
        value = descriptor.get(key)
        if value:
            attrs.append(f"{tag}[{attr}={css_string(str(value))}]")
    return attrs


def css_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    return "concat(" + ", \"'\", ".join(f"'{part}'" for part in value.split("'")) + ")"


def quality_warnings(flow: dict[str, Any]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for step in flow.get("steps", []):
        target = step.get("target") or {}
        locators = [target.get("primary"), *(target.get("candidates") or [])]
        for locator in filter(None, locators):
            value = locator.get("value", "")
            if locator.get("kind") == "css" and "nth-child" in value:
                warnings.append({"step_id": step.get("id", ""), "pattern": "nth-child", "locator": value})
            if locator.get("kind") == "xpath" and value.startswith("/"):
                warnings.append({"step_id": step.get("id", ""), "pattern": "absolute_xpath", "locator": value})
            if locator.get("kind") == "point":
                warnings.append({"step_id": step.get("id", ""), "pattern": "coordinate_fallback", "locator": value})
    return warnings
