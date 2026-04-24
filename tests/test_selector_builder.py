from web_rpa.selector_builder import build_candidates, build_target, quality_warnings


def test_test_id_is_primary():
    target = build_target({"tag": "button", "text": "Save", "testId": "save-button"})

    assert target["primary"] == {"kind": "test_id", "value": "save-button"}


def test_role_label_and_xpath_priority():
    candidates = build_candidates(
        {
            "tag": "button",
            "text": "Save",
            "role": "button",
            "cssPath": "body > div:nth-child(1) > button",
            "xpath": "/html/body/div/button",
        }
    )

    assert candidates[0] == {"kind": "role", "role": "button", "name": "Save"}
    assert candidates[-1] == {"kind": "xpath", "value": "/html/body/div/button"}


def test_quality_warnings_flag_fragile_patterns():
    flow = {
        "steps": [
            {
                "id": "s1",
                "type": "click",
                "target": {
                    "primary": {"kind": "css", "value": "div:nth-child(2)"},
                    "candidates": [{"kind": "xpath", "value": "/html/body/div"}],
                    "fingerprint": {},
                },
            }
        ]
    }

    patterns = {item["pattern"] for item in quality_warnings(flow)}
    assert patterns == {"nth-child", "absolute_xpath"}
