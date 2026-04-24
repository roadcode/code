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


class FakePage:
    def __init__(self, locators):
        self.locators = locators

    def get_by_test_id(self, value):
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


def test_resolver_reports_not_found_and_ambiguous():
    with pytest.raises(SelectorNotFound):
        LocatorResolver(FakePage({"missing": FakeLocator(0)})).resolve(
            {"primary": {"kind": "test_id", "value": "missing"}, "candidates": [], "fingerprint": {}}
        )

    with pytest.raises(SelectorAmbiguous):
        LocatorResolver(FakePage({"many": FakeLocator(2)})).resolve(
            {"primary": {"kind": "test_id", "value": "many"}, "candidates": [], "fingerprint": {}}
        )
