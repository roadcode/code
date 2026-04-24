import pytest

from web_rpa.errors import SelectorAmbiguous, SelectorNotFound
from web_rpa.locator_resolver import LocatorResolver


class FakeLocator:
    def __init__(self, count, visible=True):
        self._count = count
        self._visible = visible

    def count(self):
        return self._count

    def is_visible(self):
        return self._visible

    @property
    def first(self):
        return self


class FakePage:
    def __init__(self, locators):
        self.locators = locators

    def get_by_test_id(self, value):
        return self.locators[value]

    def get_by_text(self, value):
        return self.locators[value]

    def locator(self, value):
        return self.locators[value]


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
