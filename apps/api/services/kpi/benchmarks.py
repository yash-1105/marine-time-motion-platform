"""Governed KPI Benchmark Service (spec §11, phase-08-kpi-engine.md).

Manages peer-port benchmarks for governed KPIs.
Spec rule: Peer-port benchmark data is absent by default and recorded as such with its
source and period fields empty rather than populated with invented numbers.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models.analytics import KPI, KPIBenchmark


class KPIBenchmarkService:
    """Service for managing governed KPI peer benchmarks."""

    def __init__(self, db: Session):
        self.db = db

    def get_benchmarks_for_kpi(self, kpi_code_or_id: str) -> dict[str, Any]:
        """Retrieves benchmarks for a given KPI, or returns absent status if none configured."""
        kpi = None
        try:
            val_uuid = UUID(kpi_code_or_id)
            kpi = self.db.execute(select(KPI).where(KPI.id == val_uuid)).scalar_one_or_none()
        except ValueError:
            kpi = self.db.execute(select(KPI).where(KPI.code == kpi_code_or_id)).scalar_one_or_none()

        if not kpi:
            raise ValueError(f"KPI '{kpi_code_or_id}' not found.")

        rows = self.db.execute(
            select(KPIBenchmark).where(KPIBenchmark.kpi_id == kpi.id)
        ).scalars().all()

        if not rows:
            # Spec requirement: Peer-port benchmark data is absent and recorded as such
            # with source and period empty rather than populated with invented numbers.
            return {
                "kpi_id": str(kpi.id),
                "kpi_code": kpi.code,
                "kpi_name": kpi.name,
                "has_benchmarks": False,
                "benchmarks": [],
                "absent_notice": (
                    "Peer-port benchmark data is absent for this metric. "
                    "Source and period fields are intentionally unpopulated; no values are fabricated."
                ),
            }

        return {
            "kpi_id": str(kpi.id),
            "kpi_code": kpi.code,
            "kpi_name": kpi.name,
            "has_benchmarks": True,
            "benchmarks": [
                {
                    "id": str(b.id),
                    "peer_port": b.peer_port,
                    "benchmark_value": b.benchmark_value,
                    "source": b.source,
                    "period": b.period,
                    "notes": b.notes,
                    "created_at": b.created_at.isoformat() if b.created_at else None,
                }
                for b in rows
            ],
        }

    def list_all_benchmarks(self) -> list[dict[str, Any]]:
        """Lists all registered benchmarks across all KPIs."""
        stmt = (
            select(KPIBenchmark, KPI)
            .join(KPI, KPIBenchmark.kpi_id == KPI.id)
            .order_by(KPI.code.asc())
        )
        items = []
        for b, kpi in self.db.execute(stmt).all():
            items.append({
                "id": str(b.id),
                "kpi_id": str(kpi.id),
                "kpi_code": kpi.code,
                "kpi_name": kpi.name,
                "peer_port": b.peer_port,
                "benchmark_value": b.benchmark_value,
                "source": b.source,
                "period": b.period,
                "notes": b.notes,
            })
        return items

    def create_benchmark(
        self,
        kpi_code_or_id: str,
        peer_port: str,
        benchmark_value: float,
        source: str | None = None,
        period: str | None = None,
        notes: str | None = None,
        created_by: str = "admin",
    ) -> KPIBenchmark:
        """Admin operation to register a peer-port benchmark for a KPI."""
        kpi = None
        try:
            val_uuid = UUID(kpi_code_or_id)
            kpi = self.db.execute(select(KPI).where(KPI.id == val_uuid)).scalar_one_or_none()
        except ValueError:
            kpi = self.db.execute(select(KPI).where(KPI.code == kpi_code_or_id)).scalar_one_or_none()

        if not kpi:
            raise ValueError(f"KPI '{kpi_code_or_id}' not found.")

        benchmark = KPIBenchmark(
            kpi_id=kpi.id,
            peer_port=peer_port,
            benchmark_value=benchmark_value,
            source=source,
            period=period,
            notes=notes,
            created_by=created_by,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.db.add(benchmark)
        self.db.commit()
        return benchmark
