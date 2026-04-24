from web_rpa.replay import build_action


class FakeLocator:
    def __init__(self):
        self.calls = []

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
    def __init__(self):
        self.calls = []

    def goto(self, url, wait_until="domcontentloaded"):
        self.calls.append(("goto", url, wait_until))


def test_build_action_for_all_step_types():
    page = FakePage()
    locator = FakeLocator()
    resolver = FakeResolver(locator)

    build_action(page, resolver, {"type": "goto", "url": "http://example.test", "wait": {"state": "load"}})()
    build_action(page, resolver, {"type": "click", "target": {}})()
    build_action(page, resolver, {"type": "fill", "target": {}, "value": "alice"})()
    build_action(page, resolver, {"type": "select", "target": {}, "value": "active"})()
    build_action(page, resolver, {"type": "change", "target": {}, "value": "yes"})()
    build_action(page, resolver, {"type": "press", "target": {}, "key": "Enter"})()

    assert page.calls == [("goto", "http://example.test", "load")]
    assert locator.calls == [
        ("click",),
        ("fill", "alice"),
        ("select_option", "active"),
        ("select_option", "yes"),
        ("press", "Enter"),
    ]
