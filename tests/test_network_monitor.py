from web_rpa.network_monitor import infer_wait_after, is_meaningful_event, normalize_url_pattern


def test_static_and_noise_events_are_filtered():
    assert not is_meaningful_event({"resource_type": "image", "url": "http://x/logo.png"})
    assert not is_meaningful_event({"resource_type": "xhr", "url": "http://x/analytics/collect"})
    assert is_meaningful_event({"resource_type": "xhr", "url": "http://x/api/orders"})


def test_url_normalization_uses_wildcards():
    assert normalize_url_pattern("GET", "https://example.com/api/orders/12345/detail?ts=1") == "GET **/api/orders/*/detail*"


def test_wait_inference_prefers_url_then_response():
    assert infer_wait_after("http://a/login", "http://a/dashboard", [])["kind"] == "url"

    wait = infer_wait_after(
        "http://a/login",
        "http://a/login",
        [{"type": "response", "method": "POST", "url": "http://a/api/login", "status": 200, "resource_type": "xhr"}],
    )
    assert wait["kind"] == "response"
    assert wait["method"] == "POST"
