import json

from web_rpa.report import RunReport


def test_report_collects_steps_and_writes_json(tmp_path):
    report_path = tmp_path / "runs" / "report.json"
    report = RunReport(flow="flows/login.json", report_out=report_path)

    report.add_step({"id": "s1", "type": "goto", "status": "passed", "duration_ms": 12})
    report.finish("passed")

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["flow"] == "flows/login.json"
    assert data["status"] == "passed"
    assert data["steps"][0]["id"] == "s1"
    assert data["ended_at"]
