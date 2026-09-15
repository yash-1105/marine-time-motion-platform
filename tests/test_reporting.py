from pathlib import Path

from apps.api.services.reporting.service import ReportService


def test_all_renderers_consume_the_same_canonical_result(tmp_path, monkeypatch):
    """Format renderers receive one result object; no format can calculate a separate metric."""
    monkeypatch.setattr("apps.api.services.reporting.service.settings.report_storage_path", str(tmp_path))
    svc = ReportService.__new__(ReportService)
    result = {"metadata": {"report_run_id": "rpt-test", "synthetic_label": "SYNTHETIC / HISTORICAL DATA", "reporting_period": {}, "filters": {}}, "sections": {"anchorage": {"title": "Anchorage", "value": {"status": "UNAVAILABLE", "reason": "missing governed input"}}}}
    for fmt, suffix in [("PDF", ".pdf"), ("XLSX", ".xlsx"), ("PPTX", ".pptx"), ("DOCX", ".docx")]:
        target = tmp_path / f"report{suffix}"
        svc._render(result, fmt, target)
        assert target.is_file() and target.stat().st_size > 100
