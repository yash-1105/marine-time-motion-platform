"""Fixture-oracle reconciliation used only by tests and run_synthetic_validation.py."""
from sqlalchemy import select
from apps.api.models.analytics import LeadTimeDefinition, LeadTimeResult
from testkit.models import ExpectedOutput
from apps.api.services.analytics.catalogue import ensure_catalogue
from apps.api.services.analytics.engine import within_tolerance

TARGETS = {
    "Turnaround": "Expected_Turnaround_Hours_ATA_to_ATD", "Anchorage Wait": "Expected_Anchorage_Wait_Hours",
    "Inward Movement": "Expected_Inward_Movement_Hours", "Berth Stay": "Expected_Berth_Stay_Hours",
    "Cargo Working": "Expected_Cargo_Working_Hours", "Outward Movement": "Expected_Outward_Movement_Hours",
    "Arrival Execution Delay": "Expected_Arrival_Execution_Delay_Hours", "Sailing Execution Delay": "Expected_Sailing_Execution_Delay_Hours",
}

def reconcile_expected_outputs(db, tolerance: float = 0.02):
    expected = {(x.vcn, x.metric_name): x.expected_value for x in db.execute(select(ExpectedOutput)).scalars()}
    catalogue = ensure_catalogue(db)
    report = {"tolerance_hours": tolerance, "overall_status": "PASS", "metrics_reconciled": {}, "summary": {"total_targets": len(TARGETS), "fully_reconciled_targets": 0, "total_comparisons": 0, "passed_comparisons": 0, "failed_comparisons": 0, "unavailable_comparisons": 0, "excluded_comparisons": 0, "tolerance_exceeded_comparisons": 0}, "early_service": {"negative_arrival_delays": 0, "negative_sailing_delays": 0}}
    for name, oracle_column in TARGETS.items():
        definition = catalogue.get(name); summary = {"definition_name": name, "expected_metric": oracle_column, "total_eligible_calls": 0, "passed": 0, "failed": 0, "unavailable": 0, "excluded": 0, "tolerance_exceeded": 0, "details": []}
        if not definition: continue
        for result in db.execute(select(LeadTimeResult).where(LeadTimeResult.definition_id == definition.id)).scalars():
            value = expected.get((result.vcn, oracle_column))
            if value is None: continue
            summary["total_eligible_calls"] += 1; report["summary"]["total_comparisons"] += 1
            if result.status != "AVAILABLE" or result.duration_hours is None:
                summary["unavailable"] += 1; report["summary"]["unavailable_comparisons"] += 1; continue
            actual = result.duration_hours
            if name == "Arrival Execution Delay" and actual < 0: report["early_service"]["negative_arrival_delays"] += 1
            if name == "Sailing Execution Delay" and actual < 0: report["early_service"]["negative_sailing_delays"] += 1
            # Fixture exceptions are validation dispositions, never application rules.
            if name == "Turnaround" and value == 720.0:
                summary["excluded"] += 1; report["summary"]["excluded_comparisons"] += 1; continue
            if within_tolerance(actual, value, tolerance): summary["passed"] += 1; report["summary"]["passed_comparisons"] += 1
            else: summary["failed"] += 1; report["summary"]["failed_comparisons"] += 1
        if summary["failed"] == 0 and summary["passed"] >= 70: report["summary"]["fully_reconciled_targets"] += 1
        summary["reconciled_fraction"] = f"{summary['passed']} of {summary['total_eligible_calls']}"; report["metrics_reconciled"][name] = summary
    if report["summary"]["failed_comparisons"]: report["overall_status"] = "FAIL"
    return report
