import pytest

from web_rpa.errors import InvalidFlow, MissingVariable
from web_rpa.flow import materialize_flow, validate_flow


def base_flow():
    return {
        "version": "0.1",
        "name": "login",
        "steps": [
            {"id": "s1", "type": "goto", "url": "http://example.test"},
            {
                "id": "s2",
                "type": "fill",
                "value": "${username}",
                "target": {
                    "primary": {"kind": "label", "value": "Username"},
                    "candidates": [],
                    "fingerprint": {"tag": "input"},
                },
                "wait_after": {"kind": "none"},
            },
        ],
    }


def test_validate_and_substitute_vars():
    flow = materialize_flow(base_flow(), {"username": "alice"})

    assert flow["steps"][1]["value"] == "alice"


def test_missing_variable_fails_before_execution():
    with pytest.raises(MissingVariable):
        materialize_flow(base_flow(), {})


def test_invalid_locator_kind_rejected():
    flow = base_flow()
    flow["steps"][1]["target"]["primary"] = {"kind": "python", "value": "page.click()"}

    with pytest.raises(InvalidFlow):
        validate_flow(flow)
