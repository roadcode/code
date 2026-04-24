import pytest


@pytest.mark.pending
@pytest.mark.skip(reason="pending until Playwright browser execution is enabled in CI")
def test_record_to_run_fixture_contract_pending_browser():
    """Browser E2E contract: record fixture actions, validate flow, reset, run, assert customer state."""
    raise AssertionError("pending")
