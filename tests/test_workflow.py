from web_rpa.workflow import WorkflowBuilder


def descriptor():
    return {"tag": "input", "name": "username", "labels": ["Username"], "text": ""}


def test_initial_goto_and_fill_merge():
    builder = WorkflowBuilder(name="login", initial_url="http://example.test")
    builder.add_event({"type": "fill", "ts": 1.0, "url": "http://example.test", "descriptor": descriptor(), "value": "a"})
    builder.add_event({"type": "fill", "ts": 1.2, "url": "http://example.test", "descriptor": descriptor(), "value": "alice"})

    flow = builder.to_flow()
    assert flow["steps"][0]["type"] == "goto"
    assert len(flow["steps"]) == 2
    assert flow["steps"][1]["value"] == "alice"


def test_fill_does_not_merge_across_urls_or_fingerprints():
    builder = WorkflowBuilder(name="login", initial_url="http://example.test/login")
    builder.add_event({"type": "fill", "ts": 1.0, "url": "http://example.test/login", "descriptor": descriptor(), "value": "alice"})
    builder.add_event({"type": "fill", "ts": 1.2, "url": "http://example.test/profile", "descriptor": descriptor(), "value": "bob"})
    builder.add_event(
        {
            "type": "fill",
            "ts": 1.3,
            "url": "http://example.test/profile",
            "descriptor": {"tag": "input", "name": "email", "labels": ["Email"], "text": ""},
            "value": "bob@example.test",
        }
    )

    values = [step.get("value") for step in builder.to_flow()["steps"] if step["type"] == "fill"]
    assert values == ["alice", "bob", "bob@example.test"]


def test_click_select_and_network_wait_are_recorded():
    builder = WorkflowBuilder(name="crm", initial_url="http://example.test")
    builder.add_event({"type": "click", "ts": 1.0, "url": "http://example.test", "descriptor": {"tag": "button", "text": "Save"}})
    builder.add_event({"type": "select", "ts": 2.0, "url": "http://example.test", "descriptor": {"tag": "select", "name": "status"}, "value": "active"})
    builder.add_event(
        {
            "type": "change",
            "ts": 3.0,
            "url": "http://example.test",
            "descriptor": {"tag": "input", "name": "notify"},
            "value": "yes",
            "network_events": [
                {"type": "response", "method": "POST", "url": "http://example.test/api/save", "status": 200, "resource_type": "xhr"}
            ],
        }
    )

    steps = builder.to_flow()["steps"]
    assert [step["type"] for step in steps] == ["goto", "click", "select", "change"]
    assert steps[-1]["wait_after"]["kind"] == "response"


def test_enter_press_is_recorded():
    builder = WorkflowBuilder(name="login", initial_url="http://example.test")
    builder.add_event({"type": "press", "key": "Enter", "ts": 1.0, "url": "http://example.test", "descriptor": descriptor()})

    assert builder.to_flow()["steps"][1]["type"] == "press"
