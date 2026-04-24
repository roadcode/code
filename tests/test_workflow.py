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


def test_enter_press_is_recorded():
    builder = WorkflowBuilder(name="login", initial_url="http://example.test")
    builder.add_event({"type": "press", "key": "Enter", "ts": 1.0, "url": "http://example.test", "descriptor": descriptor()})

    assert builder.to_flow()["steps"][1]["type"] == "press"
