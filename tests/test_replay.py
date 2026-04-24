import pytest

from web_rpa.errors import SelectorNotFound
from web_rpa.report import RunReport
from web_rpa.replay import build_action, execute_steps, is_non_action_overlay_click, is_select_target, submit_click_signature


class FakeLocator:
    def __init__(self, count=1):
        self.calls = []
        self._count = count

    def count(self):
        return self._count

    def is_visible(self):
        return True

    def wait_for(self, state="visible", timeout=30000):
        self.calls.append(("wait_for", state, timeout))

    def click(self):
        self.calls.append(("click",))

    def fill(self, value):
        self.calls.append(("fill", value))

    def select_option(self, value):
        self.calls.append(("select_option", value))

    def press(self, key):
        self.calls.append(("press", key))


class FakeResolver:
    def __init__(self, locator):
        self.locator = locator

    def resolve(self, target):
        return type("Resolution", (), {"locator": self.locator})()


class FakePage:
    def __init__(self, name="page"):
        self.name = name
        self.calls = []
        self.locator_instance = FakeLocator()
        self.context = None

    def goto(self, url, wait_until="domcontentloaded"):
        self.calls.append(("goto", url, wait_until))

    def wait_for_load_state(self, state, timeout=30000):
        self.calls.append(("wait_for_load_state", state, timeout))

    def expect_popup(self, timeout=30000):
        return FakePopupInfo(self, timeout)

    def locator(self, value):
        self.calls.append(("locator", value))
        return self.locator_instance


class FakePopupInfo:
    def __init__(self, page, timeout):
        self.page = page
        self.timeout = timeout
        self.value = None

    def __enter__(self):
        self.page.calls.append(("expect_popup", self.timeout))
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.value = self.page.context.new_page()
        return False


class FakeContext:
    def __init__(self):
        self.pages = []

    def new_page(self):
        page = FakePage(name=f"page{len(self.pages) + 1}")
        page.context = self
        self.pages.append(page)
        return page


def test_build_action_for_all_step_types():
    page = FakePage()
    locator = FakeLocator()
    resolver = FakeResolver(locator)

    build_action(page, resolver, {"type": "goto", "url": "http://example.test", "wait": {"state": "load"}})()
    build_action(page, resolver, {"type": "click", "target": {}})()
    build_action(page, resolver, {"type": "fill", "target": {}, "value": "alice"})()
    build_action(page, resolver, {"type": "select", "target": {}, "value": "active"})()
    build_action(page, resolver, {"type": "change", "target": {"fingerprint": {"tag": "select"}}, "value": "yes"})()
    build_action(page, resolver, {"type": "press", "target": {}, "key": "Enter"})()

    assert page.calls == [("goto", "http://example.test", "load")]
    assert locator.calls == [
        ("click",),
        ("fill", "alice"),
        ("select_option", "active"),
        ("select_option", "yes"),
        ("press", "Enter"),
    ]


def test_new_page_action_is_only_a_switch_marker():
    page = FakePage("initial")

    result = build_action(page, FakeResolver(FakeLocator()), {"type": "new_page", "url": "http://example.test/details"})()

    assert result is page
    assert page.calls == []


def test_execute_steps_switches_to_new_page(tmp_path):
    context = FakeContext()
    page = FakePage("initial")
    page.context = context
    report = RunReport(flow="flow.json", report_out=tmp_path / "report.json")
    steps = [
        {
            "id": "s1",
            "type": "click",
            "target": {"primary": {"kind": "css", "value": "a[target=\"_blank\"]"}, "candidates": [], "fingerprint": {}},
            "wait_after": {"kind": "none"},
        },
        {"id": "s2", "type": "new_page", "url": "http://example.test/details", "wait_after": {"kind": "none"}},
        {
            "id": "s3",
            "type": "fill",
            "value": "alice",
            "target": {"primary": {"kind": "css", "value": "input[name=\"user\"]"}, "candidates": [], "fingerprint": {}},
            "wait_after": {"kind": "none"},
        },
    ]

    execute_steps(page, steps, report)

    assert [step["status"] for step in report.steps] == ["passed", "passed", "passed"]
    assert page.locator_instance.calls == [("click",)]
    assert context.pages[0].calls == [("wait_for_load_state", "domcontentloaded", 30000), ("locator", 'input[name="user"]')]
    assert context.pages[0].locator_instance.calls == [("fill", "alice")]


def test_change_on_text_input_uses_fill_not_select_option():
    locator = FakeLocator()
    resolver = FakeResolver(locator)

    build_action(
        FakePage(),
        resolver,
        {"type": "change", "target": {"fingerprint": {"tag": "input", "type": "text"}}, "value": "alice"},
    )()

    assert locator.calls == [("fill", "alice")]


def test_is_select_target_detects_select_fingerprint_or_css():
    assert is_select_target({"fingerprint": {"tag": "select"}})
    assert is_select_target({"fingerprint": {}, "primary": {"kind": "css", "value": "select[name=\"status\"]"}})
    assert not is_select_target({"fingerprint": {"tag": "input"}, "primary": {"kind": "css", "value": "input[name=\"status\"]"}})


def test_non_action_overlay_click_is_skipped(tmp_path):
    page = FakePage()
    report = RunReport(flow="flow.json", report_out=tmp_path / "report.json")
    overlay_step = {
        "id": "s1",
        "type": "click",
        "target": {
            "primary": {"kind": "css", "value": "div[id=\"ext-gen52\"]"},
            "candidates": [],
            "fingerprint": {"tag": "div", "id": "ext-gen52", "bbox": {"x": 0, "y": 0, "w": 1280, "h": 720}},
        },
        "wait_after": {"kind": "none"},
    }

    execute_steps(page, [overlay_step], report)

    assert is_non_action_overlay_click(overlay_step)
    assert report.steps[0]["status"] == "skipped"
    assert report.steps[0]["reason"] == "non-action overlay click"
    assert page.locator_instance.calls == [("wait_for", "detached", 30000)]
    assert page.calls == [("locator", 'div[id="ext-gen52"]')]


def submit_step(step_id):
    return {
        "id": step_id,
        "type": "click",
        "url": "http://example.test/login",
        "target": {
            "primary": {"kind": "css", "value": "input[id=\"loginButton\"]"},
            "candidates": [{"kind": "css", "value": "input[type=\"submit\"]"}],
            "fingerprint": {"tag": "input", "id": "loginButton", "name": "submit", "type": "submit"},
        },
        "wait_after": {"kind": "none"},
    }


def test_submit_click_signature_only_for_submit_clicks():
    assert submit_click_signature(submit_step("s1")) is not None
    assert submit_click_signature({"type": "click", "target": {"fingerprint": {"tag": "a"}}}) is None
    assert submit_click_signature({"type": "fill", "target": {"fingerprint": {"tag": "input", "type": "submit"}}}) is None


def test_execute_steps_skips_consecutive_duplicate_submit_clicks(tmp_path):
    page = FakePage()
    page.url = "http://example.test/login"
    report = RunReport(flow="flow.json", report_out=tmp_path / "report.json")

    execute_steps(page, [submit_step("s1"), submit_step("s2")], report)

    assert [step["status"] for step in report.steps] == ["passed", "skipped"]
    assert report.steps[1]["reason"] == "duplicate submit click"


def test_execute_steps_fails_instead_of_skipping_to_later_available_step(tmp_path):
    page = FakePage()
    page.url = "http://example.test/app"
    report = RunReport(flow="flow.json", report_out=tmp_path / "report.json")
    stale = {
        "id": "s1",
        "type": "click",
        "target": {
            "primary": {"kind": "css", "value": "missing"},
            "candidates": [],
            "fingerprint": {},
        },
        "wait_after": {"kind": "none"},
    }
    available = {
        "id": "s2",
        "type": "click",
        "target": {
            "primary": {"kind": "css", "value": "ok"},
            "candidates": [],
            "fingerprint": {},
        },
        "wait_after": {"kind": "none"},
    }
    page.locator_instance = {"missing": FakeLocator(count=0), "ok": FakeLocator(count=1)}

    def locator(value):
        return page.locator_instance[value]

    page.locator = locator

    with pytest.raises(SelectorNotFound):
        execute_steps(page, [stale, available], report)

    assert [step["status"] for step in report.steps] == ["failed"]
    assert report.steps[0]["id"] == "s1"


def test_execute_steps_does_not_resume_from_later_url_segment_only(tmp_path):
    page = FakePage()
    page.url = "http://example.test/portal"
    report = RunReport(flow="flow.json", report_out=tmp_path / "report.json")
    stale = {
        "id": "s1",
        "type": "click",
        "url": "http://example.test/portal",
        "target": {"primary": {"kind": "css", "value": "missing"}, "candidates": [], "fingerprint": {}},
        "wait_after": {"kind": "none"},
    }
    covered = {
        "id": "s2",
        "type": "click",
        "url": "http://example.test/portal",
        "target": {"primary": {"kind": "css", "value": "still-missing"}, "candidates": [], "fingerprint": {}},
        "wait_after": {"kind": "none"},
    }
    later = {
        "id": "s3",
        "type": "click",
        "url": "http://example.test/app",
        "target": {"primary": {"kind": "css", "value": "ok"}, "candidates": [], "fingerprint": {}},
        "wait_after": {"kind": "none"},
    }
    locators = {"missing": FakeLocator(count=0), "still-missing": FakeLocator(count=0), "ok": FakeLocator(count=1)}
    page.locator = lambda value: locators[value]

    with pytest.raises(SelectorNotFound):
        execute_steps(page, [stale, covered, later], report)

    assert [step["status"] for step in report.steps] == ["failed"]
