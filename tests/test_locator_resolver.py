import pytest

from web_rpa.errors import SelectorAmbiguous, SelectorNotFound
from web_rpa.locator_resolver import LocatorResolver


class FakeLocator:
    def __init__(self, count, visible=True, boxes=None, index=None):
        self._count = count
        self._visible = visible
        self._boxes = boxes or []
        self._index = index

    def count(self):
        return self._count

    def is_visible(self):
        return self._visible

    def nth(self, index):
        visible = self._visible
        if self._boxes:
            visible = self._boxes[index] is not None
        return FakeLocator(1, visible=visible, boxes=self._boxes, index=index)

    def bounding_box(self):
        if self._index is None or not self._boxes:
            return None
        return self._boxes[self._index]

    @property
    def first(self):
        return self


class FakePage:
    def __init__(self, locators):
        self.locators = locators
        self.frames = []
        self.main_frame = None

    def get_by_test_id(self, value):
        return self.locators[value]

    def get_by_text(self, value):
        return self.locators[value]

    def locator(self, value):
        return self.locators[value]


class FakeFrame(FakePage):
    def __init__(self, locators, url="http://frame.test"):
        super().__init__(locators)
        self.url = url


def test_resolver_falls_back_to_candidate():
    page = FakePage({"missing": FakeLocator(0), "ok": FakeLocator(1)})
    target = {
        "primary": {"kind": "test_id", "value": "missing"},
        "candidates": [{"kind": "css", "value": "ok"}],
        "fingerprint": {},
    }

    result = LocatorResolver(page).resolve(target)
    assert result.candidate == {"kind": "css", "value": "ok"}


def test_resolver_reports_not_found():
    with pytest.raises(SelectorNotFound):
        LocatorResolver(FakePage({"missing": FakeLocator(0)}), timeout_ms=0).resolve(
            {"primary": {"kind": "test_id", "value": "missing"}, "candidates": [], "fingerprint": {}}
        )


def test_resolver_reports_ambiguous_instead_of_clicking_first():
    page = FakePage({"many": FakeLocator(2)})
    with pytest.raises(SelectorAmbiguous):
        LocatorResolver(page, timeout_ms=0).resolve(
            {"primary": {"kind": "test_id", "value": "many"}, "candidates": [], "fingerprint": {}}
        )


def test_href_fingerprint_candidate_beats_broad_text_and_xpath():
    href = "https://download.openmmlab.com/mmdetection/v2.0/yolox/log.json"
    page = FakePage(
        {
            "log": FakeLocator(2),
            f'a[href="{href}"]': FakeLocator(1),
            "//a[contains(normalize-space(.), 'log')]": FakeLocator(1, visible=False),
        }
    )

    result = LocatorResolver(page, timeout_ms=0).resolve(
        {
            "primary": {"kind": "text", "value": "log"},
            "candidates": [{"kind": "xpath", "value": "//a[contains(normalize-space(.), 'log')]"}],
            "fingerprint": {"href": href},
        }
    )

    assert result.candidate == {"kind": "css", "value": f'a[href="{href}"]'}


def test_hash_href_fingerprint_does_not_beat_specific_primary():
    page = FakePage(
        {
            "ul#menu > li:nth-child(4) > div > a": FakeLocator(1),
            'a[href="#"]': FakeLocator(10),
        }
    )

    result = LocatorResolver(page, timeout_ms=0).resolve(
        {
            "primary": {"kind": "css", "value": "ul#menu > li:nth-child(4) > div > a"},
            "candidates": [{"kind": "css", "value": 'a[href="#"]'}],
            "fingerprint": {"href": "#", "text": "Provisioning"},
        }
    )

    assert result.candidate == {"kind": "css", "value": "ul#menu > li:nth-child(4) > div > a"}


def test_explicit_hash_href_candidate_is_ignored_as_generic():
    page = FakePage({"missing": FakeLocator(0), "Provisioning": FakeLocator(1), 'a[href="#"]': FakeLocator(1)})

    result = LocatorResolver(page, timeout_ms=0).resolve(
        {
            "primary": {"kind": "css", "value": "missing"},
            "candidates": [{"kind": "css", "value": 'a[href="#"]'}, {"kind": "text", "value": "Provisioning"}],
            "fingerprint": {"href": "#", "text": "Provisioning"},
        }
    )

    assert result.candidate == {"kind": "text", "value": "Provisioning"}


def test_bbox_fingerprint_narrows_ambiguous_css_candidate():
    page = FakePage(
        {
            "input[type=\"text\"]": FakeLocator(
                2,
                boxes=[
                    {"x": 400, "y": 300, "width": 200, "height": 32},
                    {"x": 16, "y": 58, "width": 208, "height": 32},
                ],
            )
        }
    )

    result = LocatorResolver(page, timeout_ms=0).resolve(
        {
            "primary": {"kind": "css", "value": "input[type=\"text\"]"},
            "candidates": [],
            "fingerprint": {"bbox": {"x": 16, "y": 58, "w": 208, "h": 32}},
        }
    )

    assert result.tried[0]["result"] == "narrowed via fingerprint"


def test_text_alias_candidate_handles_query_search_label_drift():
    page = FakePage({"查询": FakeLocator(0), "搜索": FakeLocator(1)})

    result = LocatorResolver(page, timeout_ms=0).resolve(
        {
            "primary": {"kind": "text", "value": "查询"},
            "candidates": [],
            "fingerprint": {"text": "查询"},
        }
    )

    assert result.candidate == {"kind": "text", "value": "搜索", "alias_for": "查询"}


def test_resolver_searches_child_frames():
    page = FakePage({"搜索": FakeLocator(0)})
    frame = FakeFrame({"搜索": FakeLocator(1)}, url="http://example.test/app")
    page.frames = [frame]

    result = LocatorResolver(page, timeout_ms=0).resolve(
        {
            "primary": {"kind": "text", "value": "搜索"},
            "candidates": [],
            "fingerprint": {"text": "搜索"},
        }
    )

    assert result.tried[0]["frame"] == "http://example.test/app"
