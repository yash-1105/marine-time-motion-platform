import hashlib
import json
import os
import shutil
import uuid

import polars as pl
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from apps.api.core.config import settings
from apps.api.models.canonical import (
    CargoOperation,
    Delay,
    DelayAllocation,
    EventOccurrence,
    VesselCall,
)
from apps.api.models.config import EventDefinition
from apps.api.models.ingestion import IngestionBatch, IngestionFile, RawRecord, StagingRecord
from apps.api.services.delays.mapping import map_to_canonical_category


class IngestionPipeline:
    REQUIRED_COLUMNS = {
        "VesselCalls": {"VCN", "Vessel_Name"},
        "Events": {"VCN", "Event_Name", "Event_Timestamp"},
        "Services": {"VCN", "Service_Type"},
        "CargoOps": {"VCN"},
        "Delays": {"VCN"},
    }
    GOVERNED_WORKSHEETS = frozenset(REQUIRED_COLUMNS)
    NON_GOVERNED_MESSAGE = "No supported Marine Time & Motion worksheet found."

    def __init__(self, db: Session, tenant_id: str = "default-tenant"):
        self.db = db
        self.tenant_id = tenant_id

    def calculate_checksum(self, file_path: str) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _store_original(self, file_path: str, batch_id: str, checksum: str, filename: str) -> str:
        """Copy an accepted workbook into immutable governed object-store storage.

        `ingestion_storage_path` is a local development directory and the mounted
        GCS/MinIO adapter in deployed environments. The checksum-addressed name
        makes retrying the same bytes idempotent without replacing evidence.
        """
        safe_name = os.path.basename(filename)
        destination_dir = os.path.join(settings.ingestion_storage_path, self.tenant_id, batch_id)
        os.makedirs(destination_dir, exist_ok=True)
        destination = os.path.join(destination_dir, f"{checksum}_{safe_name}")
        if not os.path.exists(destination):
            shutil.copyfile(file_path, destination)
        return destination

    def process_file(
        self,
        file_path: str,
        filename: str,
        is_synthetic: bool = False,
        dry_run: bool = False,
        force_new: bool = False,
        commit_canonical: bool = True,
    ) -> str:
        return self.process_files(
            [(file_path, filename)],
            is_synthetic=is_synthetic,
            dry_run=dry_run,
            force_new=force_new,
            commit_canonical=commit_canonical,
        )

    def process_files(
        self,
        files: list[tuple[str, str]],
        is_synthetic: bool = False,
        dry_run: bool = False,
        force_new: bool = False,
        commit_canonical: bool = True,
    ) -> str:
        """Parse a 1–15 workbook dataset group under one governed parent batch.

        The parent batch is the activation unit; individual files remain immutable
        manifests and all raw/staging records retain their source_file_id.
        """
        if not 1 <= len(files) <= 15:
            raise ValueError("A dataset group must contain between 1 and 15 workbooks")
        checksums = [self.calculate_checksum(path) for path, _ in files]
        checksum = hashlib.sha256("".join(sorted(checksums)).encode()).hexdigest()
        batch_id = str(uuid.uuid4())

        if not force_new:
            existing = self.db.execute(
                select(IngestionBatch).where(
                    IngestionBatch.file_checksum == checksum,
                    IngestionBatch.tenant_id == self.tenant_id,
                )
            ).scalar_one_or_none()

            if existing and existing.status == "COMMITTED":
                existing.file_name = files[0][1] if len(files) == 1 else f"{len(files)} workbooks"
                existing.is_active = True
                self.db.commit()
                return str(existing.batch_id)

        batch = IngestionBatch(
            batch_id=batch_id,
            file_name=files[0][1] if len(files) == 1 else f"{len(files)} workbooks",
            file_checksum=checksum,
            status="UPLOADED",
            tenant_id=self.tenant_id,
            is_synthetic=is_synthetic,
            # A group becomes active only after canonical and analytics processing
            # completes. The async worker performs the final activation.
            is_active=False,
        )
        self.db.add(batch)
        self.db.commit()

        try:
            manifests = []
            for (file_path, filename), file_checksum in zip(files, checksums, strict=True):
                manifest = IngestionFile(
                    group_batch_id=batch_id,
                    original_filename=filename,
                    file_checksum=file_checksum,
                    byte_size=__import__("os").path.getsize(file_path),
                    storage_reference=self._store_original(file_path, batch_id, file_checksum, filename),
                    parse_status="QUEUED",
                    validation_status="PENDING",
                )
                self.db.add(manifest)
                manifests.append((file_path, manifest))
            self.db.commit()
            governed_sheets: set[str] = set()
            for file_path, manifest in manifests:
                try:
                    file_governed_sheets = self._parse_to_raw(file_path, batch, manifest)
                    if file_governed_sheets:
                        governed_sheets.update(file_governed_sheets)
                        manifest.parse_status = "PARSED"
                    else:
                        # A valid workbook may be supplemental evidence rather
                        # than an operational data source. Keep its immutable
                        # manifest/checksum, but do not create raw or staging
                        # records and do not weaken validation of governed tabs.
                        manifest.parse_status = "SKIPPED"
                        manifest.validation_status = "SKIPPED"
                        manifest.error_message = self.NON_GOVERNED_MESSAGE
                    self.db.commit()
                except Exception as exc:
                    manifest.parse_status = "FAILED"
                    manifest.validation_status = "FAILED"
                    manifest.error_message = str(exc)
                    self.db.commit()
                    raise
            if not governed_sheets:
                raise ValueError("No governed worksheets were found across the uploaded files.")
            self._map_to_staging(batch)
            self._validate_staging(batch)
            for _, manifest in manifests:
                if manifest.parse_status == "PARSED":
                    manifest.validation_status = "VALIDATED"

            if dry_run:
                try:
                    self.db.begin_nested()
                    self._commit_to_canonical(batch)
                    self.db.rollback()
                except Exception:
                    self.db.rollback()
                # Status for dry run
                batch.status = "DRY_RUN_COMPLETED"
                self.db.commit()
            elif commit_canonical:
                self._commit_to_canonical(batch)
                batch.is_active = True
                self.db.commit()
            else:
                batch.status = "VALIDATED"
                self.db.commit()

            return str(batch.batch_id)
        except Exception as e:
            batch.status = "FAILED"
            batch.error_message = str(e)
            self.db.commit()
            raise e

    def _parse_to_raw(
        self,
        file_path: str,
        batch: IngestionBatch,
        source_file: IngestionFile | None = None,
    ) -> set[str]:
        # Polars/fastexcel is the deterministic parser. No AI/OCR/mapping path is
        # reachable from this governed workbook flow.
        workbook = pl.read_excel(file_path, sheet_id=0)
        seen_sheets = set(workbook).intersection(self.GOVERNED_WORKSHEETS)
        if not seen_sheets:
            return set()

        for sheet_name, df in workbook.items():
            if sheet_name not in self.GOVERNED_WORKSHEETS:
                continue
            missing_columns = self.REQUIRED_COLUMNS[sheet_name].difference(df.columns)
            if missing_columns:
                raise ValueError(f"{sheet_name} is missing required column(s): {', '.join(sorted(missing_columns))}")

            # Raw lineage is intentionally cell-level, but creating one ORM object
            # per cell makes ordinary workbooks needlessly slow over a remote
            # database connection.  Core bulk inserts preserve exactly the same
            # immutable values and source-file/sheet/row/column lineage while
            # using bounded database round trips.
            records: list[dict] = []
            for row_idx, row in enumerate(df.iter_rows(named=True), start=2):
                for col_name, val in row.items():
                    val_str = "" if val is None else str(val)
                    records.append(
                        {
                            "file_checksum": source_file.file_checksum if source_file else batch.file_checksum,
                            "worksheet_name": sheet_name,
                            "row_number": row_idx,
                            "column_name": col_name,
                            "original_value": val_str,
                            "ingestion_batch_id": batch.batch_id,
                            "source_record_id": row.get("VCN") or row.get("Source_Call_ID") or "",
                            "source_file_id": str(source_file.id) if source_file else None,
                        }
                    )

                if len(records) >= 5000:
                    self.db.execute(insert(RawRecord), records)
                    self.db.flush()
                    records = []

            if records:
                self.db.execute(insert(RawRecord), records)
                self.db.flush()

        batch.status = "PARSED"
        self.db.commit()
        return seen_sheets

    def _map_to_staging(self, batch: IngestionBatch):
        sheets = (
            self.db.execute(
                select(RawRecord.worksheet_name).where(RawRecord.ingestion_batch_id == batch.batch_id).distinct()
            )
            .scalars()
            .all()
        )

        for sheet in sheets:
            raw_records = (
                self.db.execute(
                    select(RawRecord).where(
                        RawRecord.ingestion_batch_id == batch.batch_id, RawRecord.worksheet_name == sheet
                    )
                )
                .scalars()
                .all()
            )

            row_map = {}
            for r in raw_records:
                # Row number repeats across files, so source file is part of the
                # staging identity. This is what makes file/sheet/row lineage exact.
                row_key = (r.source_file_id, r.row_number)
                if row_key not in row_map:
                    row_map[row_key] = {
                        "data": {},
                        "source_record_id": r.source_record_id,
                        "source_file_id": r.source_file_id,
                        "file_checksum": r.file_checksum,
                    }
                if isinstance(row_map[row_key], dict) and isinstance(row_map[row_key].get("data"), dict):
                    row_map[row_key]["data"][str(r.column_name)] = r.original_value  # type: ignore

            staging_records: list[dict] = []
            for (_, row_idx), row_info in row_map.items():
                parsed_data = row_info["data"]
                canonical_table = ""
                if sheet == "VesselCalls":
                    canonical_table = "vessel_call"
                elif sheet == "Events":
                    canonical_table = "event_occurrence"
                elif sheet == "Services":
                    canonical_table = "service_request"
                elif sheet == "CargoOps":
                    canonical_table = "cargo_ops"
                elif sheet == "Delays":
                    canonical_table = "delay"

                staging_records.append(
                    {
                        "file_checksum": row_info["file_checksum"],
                        "worksheet_name": sheet,
                        "row_number": row_idx,
                        "parsed_data": parsed_data,
                        "errors": {},
                        "ingestion_batch_id": batch.batch_id,
                        "validation_status": "PENDING",
                        "source_record_id": row_info["source_record_id"],
                        "canonical_table": canonical_table,
                        "source_file_id": row_info["source_file_id"],
                    }
                )

            if staging_records:
                self.db.execute(insert(StagingRecord), staging_records)
            self.db.commit()

        batch.status = "MAPPED"
        self.db.commit()

    def _validate_staging(self, batch: IngestionBatch):
        rows = (
            self.db.execute(select(StagingRecord).where(StagingRecord.ingestion_batch_id == batch.batch_id))
            .scalars()
            .all()
        )
        if not any(row.canonical_table == "vessel_call" for row in rows):
            raise ValueError("Dataset group requires at least one VesselCalls worksheet")
        seen: set[tuple[str, str]] = set()
        for row in rows:
            fingerprint = json.dumps(row.parsed_data, sort_keys=True, default=str, separators=(",", ":"))
            key = (row.canonical_table, fingerprint)
            if key in seen:
                row.validation_status = "DUPLICATE"
                row.errors = {"duplicate": "Exact duplicate row in dataset group"}
            else:
                row.validation_status = "VALID"
                seen.add(key)
        batch.status = "VALIDATED"
        self.db.commit()

    def _commit_to_canonical(self, batch: IngestionBatch, completion_status: str = "COMMITTED"):
        vessel_records = (
            self.db.execute(
                select(StagingRecord).where(
                    StagingRecord.ingestion_batch_id == batch.batch_id,
                    StagingRecord.canonical_table == "vessel_call",
                    StagingRecord.validation_status.notin_(["DUPLICATE", "EXCLUDED"]),
                )
            )
            .scalars()
            .all()
        )

        vcn_to_id = {}
        vessels_to_add = []
        for r in vessel_records:
            pd = r.parsed_data
            vcn = pd.get("VCN")

            def get_val(pd_dict, key):
                val = pd_dict.get(key)
                return val if val != "" else None

            def get_float(pd_dict, key):
                val = get_val(pd_dict, key)
                if val:
                    try:
                        return float(val)
                    except Exception:
                        return None
                return None

            vc = VesselCall(
                source_lineage_id=f"{r.source_file_id}:{r.worksheet_name}:{r.row_number}",
                tenant_id=batch.tenant_id,
                vessel_name=get_val(pd, "Vessel_Name") or "UNKNOWN",
                imo_number=get_val(pd, "IMO_Number"),
                vcn=vcn,
                vessel_type=get_val(pd, "Vessel_Type"),
                vessel_size_teu=get_float(pd, "Vessel_Size_TEU"),
                flag=get_val(pd, "Flag"),
                last_port_of_call=get_val(pd, "Last_Port_Of_Call"),
                next_port_of_call=get_val(pd, "Next_Port_Of_Call"),
                reason_for_visit=get_val(pd, "Reason_For_Visit"),
                cargo_type=get_val(pd, "Cargo_Type"),
                quantity_value=get_float(pd, "Planned_Quantity"),
                grt=get_float(pd, "GRT"),
                loa_value=get_float(pd, "LOA_Value"),
                dwt=get_float(pd, "DWT"),
            )
            self.db.add(vc)
            vessels_to_add.append((vcn, vc))

        self.db.flush()

        for vcn, vc in vessels_to_add:
            if vcn and vcn not in vcn_to_id:
                vcn_to_id[vcn] = vc.id

        event_records = (
            self.db.execute(
                select(StagingRecord).where(
                    StagingRecord.ingestion_batch_id == batch.batch_id,
                    StagingRecord.canonical_table == "event_occurrence",
                    StagingRecord.validation_status.notin_(["DUPLICATE", "EXCLUDED"]),
                )
            )
            .scalars()
            .all()
        )

        event_defs = self.db.execute(select(EventDefinition)).scalars().all()
        event_def_map = {e.name: e.id for e in event_defs}

        # Auto-register any event names from the workbook that are not yet in config.event_definition.
        # This ensures upstream event names (e.g. ANCHORAGE_ARRIVAL, PILOT_ON_BOARD_ARRIVAL) are
        # always resolvable rather than silently dropped.
        seen_event_names: set[str] = set()
        for r_scan in event_records:
            en = r_scan.parsed_data.get("Event_Name")
            if en and en not in event_def_map:
                seen_event_names.add(en)
        for en in sorted(seen_event_names):
            new_def = EventDefinition(name=en, category="Ingested", description=f"Auto-registered from workbook: {en}")
            self.db.add(new_def)
        if seen_event_names:
            self.db.flush()
            # Rebuild the lookup map with newly created definitions
            event_defs = self.db.execute(select(EventDefinition)).scalars().all()
            event_def_map = {e.name: e.id for e in event_defs}

        import pytz
        from dateutil import parser

        event_counters = {}
        for r in event_records:
            pd = r.parsed_data
            vcn = pd.get("VCN")
            vc_id = vcn_to_id.get(vcn)

            if not vc_id:
                r.validation_status = "QUARANTINED"
                r.errors = {"VCN": "Orphan event: VCN not found"}
                continue

            event_name = pd.get("Event_Name")
            event_def_id = event_def_map.get(event_name)

            timestamp_str = pd.get("Event_Timestamp")
            tz_str = pd.get("Timezone", "Africa/Johannesburg")

            parsed_tz = None
            utc_val = None
            if timestamp_str and timestamp_str != "":
                try:
                    dt = parser.parse(timestamp_str)
                    tz = pytz.timezone(tz_str)
                    if dt.tzinfo is None:
                        dt = tz.localize(dt)
                    utc_val = dt.astimezone(pytz.utc)
                    parsed_tz = dt
                except Exception:
                    pass

            scope = "ARRIVAL"
            if event_name and ("SAILING" in event_name or "DEPARTURE" in event_name or "OUT" in event_name):
                scope = "SAILING"
            elif event_name and "SHIFT" in event_name:
                scope = "SHIFTING"

            confidence_str = pd.get("Confidence_Score")
            try:
                confidence = float(confidence_str) if confidence_str and confidence_str != "" else None
            except Exception:
                confidence = None

            if utc_val and event_def_id:
                ev = EventOccurrence(
                    source_lineage_id=f"{r.source_file_id}:{r.worksheet_name}:{r.row_number}",
                    vessel_call_id=vc_id,
                    event_definition_id=event_def_id,
                    occurrence_index=(
                        event_counters.update({(vc_id, event_def_id): event_counters.get((vc_id, event_def_id), 0) + 1})
                        or event_counters[(vc_id, event_def_id)]
                    ),
                    movement_scope=scope,
                    original_string=timestamp_str,
                    parsed_value=parsed_tz,
                    source_timezone=tz_str,
                    utc_value=utc_val,
                    capture_method="SYSTEM",
                    confidence=confidence,
                    verification_status=pd.get("Verification_Status") or None,
                    source_system=pd.get("Source_System"),
                    source_record_id=pd.get("Event_ID"),
                    ingestion_batch_id=batch.batch_id,
                    is_quarantined=False,
                )
                self.db.add(ev)

        batch_staging = (
            self.db.execute(select(StagingRecord).where(StagingRecord.ingestion_batch_id == batch.batch_id))
            .scalars()
            .all()
        )
        from apps.api.models.canonical import ServiceAssignment, ServiceExecution, ServiceRequest

        def dt_parse(dt_str):
            import pytz
            from dateutil import parser

            if not dt_str:
                return None
            try:
                dt = parser.parse(dt_str)
                if dt.tzinfo is None:
                    dt = pytz.timezone("Africa/Johannesburg").localize(dt)
                return dt.astimezone(pytz.utc)
            except Exception:
                return None

        service_records = [
            r
            for r in batch_staging
            if r.canonical_table == "service_request" and r.validation_status not in {"DUPLICATE", "EXCLUDED"}
        ]
        for r in service_records:
            pd_data = r.parsed_data
            vcn = pd_data.get("VCN")
            vc_id = vcn_to_id.get(vcn)
            if not vc_id:
                continue

            req = ServiceRequest(
                source_lineage_id=f"{r.source_file_id}:{r.worksheet_name}:{r.row_number}",
                vessel_call_id=vc_id,
                service_type=pd_data.get("Service_Type", "Unknown"),
                requested_time=dt_parse(pd_data.get("Requested_Time")),
                movement_type=pd_data.get("Movement_Type"),  # Phase 07
                submission_time=dt_parse(pd_data.get("Submission_Time")),  # Phase 07
            )
            self.db.add(req)
            self.db.flush()

            ass = ServiceAssignment(
                source_lineage_id=f"{r.source_file_id}:{r.worksheet_name}:{r.row_number}",
                service_request_id=req.id,
                scheduled_time=dt_parse(pd_data.get("Scheduled_Time")),
                assigned_resource_id=pd_data.get("Resource_Assigned"),
                resource_type=pd_data.get("Service_Type"),
            )
            self.db.add(ass)
            self.db.flush()

            exe = ServiceExecution(
                source_lineage_id=f"{r.source_file_id}:{r.worksheet_name}:{r.row_number}",
                service_assignment_id=ass.id,
                served_time=dt_parse(pd_data.get("Served_Time")),
                execution_status=pd_data.get("Data_Status"),
            )
            self.db.add(exe)

        delay_records = [
            r
            for r in batch_staging
            if r.canonical_table == "delay" and r.validation_status not in {"DUPLICATE", "EXCLUDED"}
        ]
        for r in delay_records:
            pd_data = r.parsed_data
            vcn = pd_data.get("VCN")
            vc_id = vcn_to_id.get(vcn)
            if not vc_id:
                continue

            def float_val(val_str):
                if not val_str:
                    return None
                try:
                    return float(val_str)
                except Exception:
                    return None

            val = float_val(pd_data.get("Duration_Hours") or pd_data.get("Delay_Hours"))
            sched_dt = dt_parse(pd_data.get("Scheduled_Time"))
            served_dt = dt_parse(pd_data.get("Served_Time"))
            recalc_val = None
            has_mismatch = False
            reconcil_notes = None
            if sched_dt and served_dt:
                recalc_val = round((served_dt - sched_dt).total_seconds() / 3600.0, 4)
                if val is not None and round(abs(recalc_val - val), 6) > 0.02:
                    has_mismatch = True
                    reconcil_notes = f"Stated: {val}h vs Recalculated: {recalc_val}h"

            dur_val = val if val is not None else (recalc_val if recalc_val is not None else 0.0)
            reason_str = str(pd_data.get("Delay_Reason") or "").strip()
            cat_str = str(pd_data.get("Delay_Category") or "").strip()
            canon_cat = map_to_canonical_category(cat_str, reason_str)
            cause_status = str(pd_data.get("Cause_Status") or "Confirmed").strip()
            confidence_str = str(pd_data.get("Confidence") or "High").strip()
            resolution_status = str(pd_data.get("Resolution_Status") or "Open").strip()

            requires_review = False
            if dur_val > 0 and (not reason_str or not cat_str):
                requires_review = True

            d = Delay(
                source_lineage_id=f"{r.source_file_id}:{r.worksheet_name}:{r.row_number}",
                vessel_call_id=vc_id,
                source_delay_id=pd_data.get("Delay_ID"),
                movement_stage=pd_data.get("Movement_Type", "Unknown"),
                total_duration_hours=dur_val,
                is_early_service=(dur_val < 0),
                scheduled_time=sched_dt,
                served_time=served_dt,
                delay_hours=val,
                recalculated_delay_hours=recalc_val,
                delay_reason=reason_str if reason_str else None,
                source_category=cat_str if cat_str else None,
                canonical_category=canon_cat,
                cause_status=cause_status,
                confidence=confidence_str,
                resolution_status=resolution_status,
                has_reconciliation_mismatch=has_mismatch,
                reconciliation_notes=reconcil_notes,
                requires_reason_review=requires_review,
            )
            self.db.add(d)
            self.db.flush()

            alloc = DelayAllocation(
                delay_id=d.id,
                cause=canon_cat,
                canonical_category=canon_cat,
                reason=reason_str if reason_str else None,
                duration_hours=dur_val,
                is_primary=True,
                cause_status="CONFIRMED" if cause_status.lower() == "confirmed" else "INFERRED",
                confidence=1.0
                if confidence_str.lower() == "high"
                else (0.7 if confidence_str.lower() == "medium" else 0.5),
                inference_evidence=None,
                human_review_state="APPROVED" if cause_status.lower() == "confirmed" else "PENDING_REVIEW",
            )
            self.db.add(alloc)

        cargo_records = [
            r
            for r in batch_staging
            if r.canonical_table == "cargo_ops" and r.validation_status not in {"DUPLICATE", "EXCLUDED"}
        ]
        for r in cargo_records:
            pd_data = r.parsed_data
            vcn = pd_data.get("VCN")
            vc_id = vcn_to_id.get(vcn)
            if not vc_id:
                continue

            def parse_flt(val_str):
                if not val_str:
                    return None
                try:
                    return float(val_str)
                except (TypeError, ValueError):
                    return None

            def parse_int(val_str):
                if not val_str:
                    return None
                try:
                    return int(float(val_str))
                except (TypeError, ValueError):
                    return None

            cg = CargoOperation(
                source_lineage_id=f"{r.source_file_id}:{r.worksheet_name}:{r.row_number}",
                vessel_call_id=vc_id,
                operation_id=pd_data.get("Cargo_Operation_ID"),
                cargo_type=pd_data.get("Cargo_Type"),
                operation_type=pd_data.get("Operation_Type"),
                planned_quantity=parse_flt(pd_data.get("Planned_Quantity")),
                unit=pd_data.get("Unit"),
                cargo_start=dt_parse(pd_data.get("Cargo_Start")),
                cargo_end=dt_parse(pd_data.get("Cargo_End")),
                working_hours=parse_flt(pd_data.get("Working_Hours")),
                resources_deployed=parse_int(pd_data.get("Resources_Deployed")),
                downtime_hours=parse_flt(pd_data.get("Downtime_Hours")),
                actual_quantity=parse_flt(pd_data.get("Actual_Quantity")),
                data_status=pd_data.get("Data_Status"),
            )
            self.db.add(cg)

            # Update vessel_call quantity_unit and quantity_value from cargo ops
            vc = self.db.query(VesselCall).filter_by(id=vc_id).first()
            if vc:
                if pd_data.get("Unit"):
                    vc.quantity_unit = pd_data.get("Unit")
                if parse_flt(pd_data.get("Actual_Quantity")) is not None:
                    vc.quantity_value = parse_flt(pd_data.get("Actual_Quantity"))

        batch.status = completion_status
        self.db.commit()
