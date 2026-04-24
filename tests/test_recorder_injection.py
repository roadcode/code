from pathlib import Path


def test_injected_recorder_contains_install_guard_and_events():
    script = Path("web_rpa/injected_recorder.js").read_text(encoding="utf-8")

    assert "__webRpaRecorderInstalled" in script
    for event in ["click", "input", "change", "keydown", "submit"]:
        assert f'addEventListener("{event}"' in script
    assert "closestInteractive" in script
    assert "selectorCounts" in script
    assert "__rpa_record" in script
