import pytest

from web_rpa.wait_manager import WaitManager


class FakePage:
    def __init__(self):
        self.waited = None
        self.order = []

    def wait_for_url(self, pattern, timeout=30000):
        self.order.append("wait_for_url")
        self.waited = (pattern, timeout)


class FakeResponseContext:
    def __init__(self, page):
        self.page = page

    def __enter__(self):
        self.page.order.append("expect_enter")

    def __exit__(self, exc_type, exc, tb):
        self.page.order.append("expect_exit")


class FakeResponsePage(FakePage):
    def expect_response(self, predicate, timeout=30000):
        self.order.append(("expect_response", timeout))
        self.predicate = predicate
        return FakeResponseContext(self)


class FakeLocator:
    def __init__(self, page):
        self.page = page

    def wait_for(self, state, timeout=30000):
        self.page.order.append(("locator_wait", state, timeout))


class FakeResolver:
    def __init__(self, page):
        self.page = page

    def materialize(self, locator):
        self.page.order.append(("materialize", locator))
        return FakeLocator(self.page)


def test_none_wait_only_runs_action():
    page = FakePage()

    result = WaitManager().run_action_with_waits(page, {"wait_after": {"kind": "none"}}, lambda: page.order.append("action"))

    assert result is None
    assert page.order == ["action"]


def test_url_wait_runs_after_action():
    page = FakePage()

    WaitManager().run_action_with_waits(
        page,
        {"wait_after": {"kind": "url", "pattern": "**/done", "timeout": 100}},
        lambda: page.order.append("action"),
    )

    assert page.order == ["action", "wait_for_url"]
    assert page.waited == ("**/done", 100)


def test_response_wait_registers_before_action():
    page = FakeResponsePage()

    WaitManager().run_action_with_waits(
        page,
        {"wait_after": {"kind": "response", "method": "POST", "url_pattern": "**/api/save", "status": [200], "timeout": 123}},
        lambda: page.order.append("action"),
    )

    assert page.order == [("expect_response", 123), "expect_enter", "action", "expect_exit"]


def test_locator_waits_run_after_action():
    page = FakePage()

    WaitManager(resolver_factory=FakeResolver).run_action_with_waits(
        page,
        {"wait_after": {"kind": "locator_visible", "locator": {"kind": "text", "value": "Done"}, "timeout": 50}},
        lambda: page.order.append("action"),
    )

    assert page.order == ["action", ("materialize", {"kind": "text", "value": "Done"}), ("locator_wait", "visible", 50)]


def test_composite_all_and_any_waits():
    page = FakePage()
    manager = WaitManager(resolver_factory=FakeResolver)

    manager.run_action_with_waits(
        page,
        {
            "wait_after": {
                "kind": "composite",
                "mode": "all",
                "items": [
                    {"kind": "url", "pattern": "**/done", "timeout": 10},
                    {"kind": "locator_hidden", "locator": {"kind": "text", "value": "Loading"}, "timeout": 20},
                ],
            }
        },
        lambda: page.order.append("action"),
    )

    assert page.order == [
        "action",
        "wait_for_url",
        ("materialize", {"kind": "text", "value": "Loading"}),
        ("locator_wait", "hidden", 20),
    ]


def test_programming_errors_are_not_wrapped_as_wait_timeout():
    with pytest.raises(TypeError):
        WaitManager().run_action_with_waits(FakePage(), {"wait_after": {"kind": "none"}}, lambda: (_ for _ in ()).throw(TypeError("bug")))
