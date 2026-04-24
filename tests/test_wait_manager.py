from web_rpa.wait_manager import WaitManager


class FakePage:
    def __init__(self):
        self.waited = None

    def wait_for_url(self, pattern, timeout=30000):
        self.waited = (pattern, timeout)


def test_url_wait_runs_after_action():
    page = FakePage()
    order = []

    WaitManager().run_action_with_waits(
        page,
        {"wait_after": {"kind": "url", "pattern": "**/done", "timeout": 100}},
        lambda: order.append("action"),
    )

    assert order == ["action"]
    assert page.waited == ("**/done", 100)
