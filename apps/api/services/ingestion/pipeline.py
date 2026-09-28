import hashlib
import json
import logging
import os
import re
import shutil
import uuid
from datetime import datetime
from zipfile import BadZipFile

import pytz
from dateutil import parser as date_parser
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
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
from apps.api.services.ingestion.standardization import StandardizationRegistry

logger = logging.getLogger(__name__)


class WorkbookIngestionError(ValueError):
    """A safe, user-facing workbook error with structured diagnostic context."""

    def __init__(
        self,
        message: str,
        *,
        workbook: str | None = None,
        worksheet: str | None = None,
        stage: str = "workbook_inspection",
        batch_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.safe_message = message
        self.workbook = workbook
        self.worksheet = worksheet
        self.stage = stage
        self.batch_id = batch_id


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
    DATETIME_COLUMNS = {
        "Events": {"Event_Timestamp"},
        "Services": {"Submission_Time", "Requested_Time", "Scheduled_Time", "Served_Time"},
        "CargoOps": {"Cargo_Start", "Cargo_End"},
        "Delays": {"Scheduled_Time", "Served_Time"},
    }
    CANONICAL_TABLES = {
        "VesselCalls": "vessel_call",
        "Events": "event_occurrence",
        "Services": "service_request",
        "CargoOps": "cargo_ops",
        "Delays": "delay",
    }
    HEADER_SCAN_LIMIT = 50

    def __init__(self, db: Session, tenant_id: str = "default-tenant"):
        self.db = db
        self.tenant_id = tenant_id
        self.standardization = StandardizationRegistry()

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
                    has_invalid_rows = self.db.execute(
                        select(StagingRecord.id)
                        .where(
                            StagingRecord.ingestion_batch_id == batch.batch_id,
                            StagingRecord.source_file_id == str(manifest.id),
                            StagingRecord.validation_status == "INVALID",
                        )
                        .limit(1)
                    ).scalar_one_or_none()
                    manifest.validation_status = "VALIDATED_WITH_ISSUES" if has_invalid_rows else "VALIDATED"

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
        filename = source_file.original_filename if source_file else os.path.basename(file_path)
        try:
            # data_only=True consumes cached formula values without executing any
            # spreadsheet code. The parser remains deterministic and non-AI.
            workbook = load_workbook(file_path, read_only=False, data_only=True)
        except (InvalidFileException, BadZipFile, OSError, ValueError) as exc:
            raise WorkbookIngestionError(
                f"Workbook '{filename}' is corrupt or unsupported.",
                workbook=filename,
                stage="open_workbook",
                batch_id=str(batch.batch_id),
            ) from exc

        seen_sheets: set[str] = set()
        skipped_sheets: list[str] = []
        try:
            for sheet in workbook.worksheets:
                detection = self._detect_header(sheet)
                if detection is None:
                    exact_target = self._target_from_sheet_name(sheet.title)
                    if exact_target and self._sheet_has_content(sheet):
                        best_headers = self._best_header_values(sheet, exact_target)
                        normalized_columns = {
                            self.standardization.canonical_column(exact_target, column) for column in best_headers
                        }
                        missing_columns = self.REQUIRED_COLUMNS[exact_target].difference(normalized_columns)
                        raise WorkbookIngestionError(
                            f"Worksheet '{sheet.title}' in '{filename}' is missing required column(s): "
                            f"{', '.join(sorted(missing_columns))}",
                            workbook=filename,
                            worksheet=sheet.title,
                            stage="header_detection",
                            batch_id=str(batch.batch_id),
                        )
                    if self._sheet_has_content(sheet):
                        skipped_sheets.append(sheet.title)
                    continue

                target, header_row, headers = detection
                seen_sheets.add(target)
                self._write_sheet_raw_records(
                    sheet=sheet,
                    target=target,
                    header_row=header_row,
                    headers=headers,
                    batch=batch,
                    source_file=source_file,
                )
        finally:
            workbook.close()

        if source_file is not None and seen_sheets and skipped_sheets:
            source_file.error_message = f"Skipped unrecognized worksheet(s): {', '.join(skipped_sheets)}."

        batch.status = "PARSED"
        self.db.commit()
        return seen_sheets

    @staticmethod
    def _sheet_has_content(sheet) -> bool:
        for row in sheet.iter_rows(
            min_row=1, max_row=min(sheet.max_row, IngestionPipeline.HEADER_SCAN_LIMIT), values_only=True
        ):
            if any(value not in {None, ""} for value in row):
                return True
        return False

    def _target_from_sheet_name(self, sheet_name: str) -> str | None:
        token = "".join(character.lower() for character in sheet_name if character.isalnum())
        for target in self.GOVERNED_WORKSHEETS:
            if token == "".join(character.lower() for character in target if character.isalnum()):
                return target
        return None

    def _classify_headers(self, headers: list[str], sheet_name: str) -> tuple[str, int] | None:
        exact_target = self._target_from_sheet_name(sheet_name)
        candidates: list[tuple[int, str]] = []
        for target in self.GOVERNED_WORKSHEETS:
            recognized = self.standardization.recognized_columns(target, headers)
            if not self.REQUIRED_COLUMNS[target].issubset(recognized):
                continue
            # CargoOps and Delays both permit VCN as their only mandatory field;
            # require one target-specific recognizable header before mapping a
            # renamed sheet so an arbitrary VCN list is never silently guessed.
            if target in {"CargoOps", "Delays"} and not exact_target and len(recognized - {"VCN"}) < 1:
                continue
            candidates.append((len(recognized), target))
        if exact_target:
            exact = next((candidate for candidate in candidates if candidate[1] == exact_target), None)
            return (exact[1], exact[0]) if exact else None
        if not candidates:
            return None
        best_score = max(score for score, _ in candidates)
        best = [target for score, target in candidates if score == best_score]
        if len(best) != 1:
            return None
        return best[0], best_score

    def _detect_header(self, sheet) -> tuple[str, int, list[tuple[int, str]]] | None:
        best: tuple[int, str, int, list[tuple[int, str]]] | None = None
        max_row = min(sheet.max_row, self.HEADER_SCAN_LIMIT)
        max_column = min(sheet.max_column, 512)
        for row_number, row in enumerate(
            sheet.iter_rows(min_row=1, max_row=max_row, max_col=max_column, values_only=True), start=1
        ):
            raw_headers = [(index, str(value)) for index, value in enumerate(row, start=1) if value not in {None, ""}]
            if not raw_headers:
                continue
            classified = self._classify_headers([value for _, value in raw_headers], sheet.title)
            if classified is None:
                continue
            target, score = classified
            candidate = (score, target, row_number, raw_headers)
            if best is None or score > best[0]:
                best = candidate
        if best is None:
            return None
        _, target, row_number, raw_headers = best
        counts: dict[str, int] = {}
        headers: list[tuple[int, str]] = []
        for column_index, value in raw_headers:
            base = value
            duplicate_key = base.strip().casefold()
            counts[duplicate_key] = counts.get(duplicate_key, 0) + 1
            suffix = f"__duplicate_{counts[duplicate_key]}" if counts[duplicate_key] > 1 else ""
            headers.append((column_index, f"{base}{suffix}"))
        return target, row_number, headers

    def _best_header_values(self, sheet, target: str) -> list[str]:
        best: tuple[int, list[str]] = (0, [])
        for row in sheet.iter_rows(
            min_row=1,
            max_row=min(sheet.max_row, self.HEADER_SCAN_LIMIT),
            max_col=min(sheet.max_column, 512),
            values_only=True,
        ):
            headers = [str(value).strip() for value in row if value not in {None, ""}]
            score = len(self.standardization.recognized_columns(target, headers))
            if score > best[0]:
                best = (score, headers)
        return best[1]

    def _write_sheet_raw_records(
        self, *, sheet, target: str, header_row: int, headers: list[tuple[int, str]], batch, source_file
    ) -> None:
        records: list[dict] = []
        recognized_columns = self.standardization.recognized_columns(target, [header for _, header in headers])
        blank_run = 0
        for row_number in range(header_row + 1, sheet.max_row + 1):
            values = {header: sheet.cell(row=row_number, column=column_index).value for column_index, header in headers}
            if not any(value not in {None, ""} for value in values.values()):
                blank_run += 1
                continue
            preceding_blank_rows = blank_run
            blank_run = 0
            normalized = self.standardization.normalize_row(target, values)
            governed_values = [
                value
                for canonical, value in normalized.items()
                if canonical in recognized_columns and value not in {None, ""}
            ]
            # Require at least one recognized governed value. This keeps footer
            # notes/instructions out of the operational population.
            if not governed_values:
                continue
            if (
                preceding_blank_rows
                and len(governed_values) == 1
                and sum(value not in {None, ""} for value in values.values()) == 1
            ):
                continue
            source_record_id = str(normalized.get("VCN") or normalized.get("Source_Call_ID") or "")
            for column_name, value in values.items():
                canonical = self.standardization.canonical_column(target, column_name)
                value_string = self.standardization.source_value(
                    value, is_datetime_column=canonical in self._datetime_columns(target)
                )
                records.append(
                    {
                        "file_checksum": source_file.file_checksum if source_file else batch.file_checksum,
                        "worksheet_name": sheet.title,
                        "row_number": row_number,
                        "column_name": column_name,
                        "original_value": value_string,
                        "ingestion_batch_id": batch.batch_id,
                        "source_record_id": source_record_id,
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

    def _map_to_staging(self, batch: IngestionBatch):
        source_sheets = self.db.execute(
            select(RawRecord.source_file_id, RawRecord.worksheet_name)
            .where(RawRecord.ingestion_batch_id == batch.batch_id)
            .distinct()
        ).all()

        for source_file_id, sheet in source_sheets:
            raw_records = (
                self.db.execute(
                    select(RawRecord).where(
                        RawRecord.ingestion_batch_id == batch.batch_id,
                        RawRecord.source_file_id == source_file_id,
                        RawRecord.worksheet_name == sheet,
                    )
                )
                .scalars()
                .all()
            )
            target_result = self._classify_headers([str(record.column_name) for record in raw_records], sheet)
            if target_result is None:
                raise WorkbookIngestionError(
                    f"Worksheet '{sheet}' could not be mapped unambiguously after parsing.",
                    worksheet=sheet,
                    stage="mapping",
                    batch_id=str(batch.batch_id),
                )
            target, _ = target_result

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
                parsed_data = self.standardization.normalize_row(target, row_info["data"])
                canonical_table = self.CANONICAL_TABLES[target]

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
            timestamp_errors = self._timestamp_errors(row)
            if timestamp_errors:
                row.validation_status = "INVALID"
                row.errors = {"invalid_timestamps": timestamp_errors}
            elif key in seen:
                row.validation_status = "DUPLICATE"
                row.errors = {"duplicate": "Exact duplicate row in dataset group"}
            else:
                row.validation_status = "VALID"
                seen.add(key)
        batch.status = "VALIDATED"
        self.db.commit()

    def _timestamp_errors(self, row: StagingRecord) -> list[str]:
        target = next((name for name, table in self.CANONICAL_TABLES.items() if table == row.canonical_table), None)
        if target is None:
            return []
        failures: list[str] = []
        for column in self._datetime_columns(target):
            value = row.parsed_data.get(column)
            if value in {None, ""}:
                continue
            if self.parse_datetime(value) is None:
                failures.append(f"Column '{column}' contains an invalid or ambiguous timestamp: {value!s}")
        return failures

    def _datetime_columns(self, target: str) -> set[str]:
        columns = set(self.DATETIME_COLUMNS.get(target, set()))
        if target == "CargoOps":
            columns.update(
                self.standardization.BERTH_TARGET_COLUMNS.get(field, field)
                for field in self.standardization.berth_datetime_fields
            )
        return columns

    @staticmethod
    def parse_datetime(value, timezone_name: str = "Africa/Johannesburg"):
        if value in {None, ""}:
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
            source = str(value).strip()
            # A time without a governed date context is not safe to guess.
            if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:AM|PM)?", source, re.IGNORECASE):
                return None
            slash_date = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})(?:\D|$)", source)
            if slash_date and int(slash_date.group(1)) <= 12 and int(slash_date.group(2)) <= 12:
                return None
            try:
                parsed = date_parser.parse(source, fuzzy=False)
            except (ValueError, TypeError, OverflowError):
                return None
        try:
            if parsed.tzinfo is None:
                parsed = pytz.timezone(timezone_name).localize(parsed)
            return parsed.astimezone(pytz.utc)
        except (ValueError, pytz.UnknownTimeZoneError):
            return None

    def _commit_to_canonical(self, batch: IngestionBatch, completion_status: str = "COMMITTED"):
        vessel_records = (
            self.db.execute(
                select(StagingRecord).where(
                    StagingRecord.ingestion_batch_id == batch.batch_id,
                    StagingRecord.canonical_table == "vessel_call",
                    StagingRecord.validation_status.notin_(["DUPLICATE", "EXCLUDED", "INVALID"]),
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
                license_number=get_val(pd, "License_Number"),
                vessel_name=get_val(pd, "Vessel_Name") or "UNKNOWN",
                imo_number=get_val(pd, "IMO_Number"),
                vcn=vcn,
                vessel_type=get_val(pd, "Vessel_Type"),
                vessel_size_teu=get_float(pd, "Vessel_Size_TEU"),
                flag=get_val(pd, "Flag"),
                last_port_of_call=get_val(pd, "Last_Port_Of_Call"),
                next_port_of_call=get_val(pd, "Next_Port_Of_Call"),
                port_of_lading=get_val(pd, "Port_Of_Lading"),
                port_of_discharge=get_val(pd, "Port_Of_Discharge"),
                reason_for_visit=get_val(pd, "Reason_For_Visit"),
                cargo_type=get_val(pd, "Cargo_Type"),
                commodity=get_val(pd, "Commodity"),
                quantity_value=get_float(pd, "Planned_Quantity"),
                grt=get_float(pd, "GRT"),
                loa_value=get_float(pd, "LOA_Value"),
                dwt=get_float(pd, "DWT"),
                forward_draft_value=get_float(pd, "Forward_Draft"),
                aft_draft_value=get_float(pd, "Aft_Draft"),
                call_sign=get_val(pd, "Call_Sign"),
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
                    StagingRecord.validation_status.notin_(["DUPLICATE", "EXCLUDED", "INVALID"]),
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

        event_counters = {}
        event_keys_with_source: set[tuple[object, object]] = set()
        for r in event_records:
            pd = r.parsed_data
            vcn = pd.get("VCN")
            vc_id = vcn_to_id.get(vcn)

            if not vc_id:
                r.validation_status = "QUARANTINED"
                r.errors = {"VCN": "Orphan event: VCN not found"}
                continue

            source_event_name = pd.get("Event_Name")
            event_name = self.standardization.canonical_event_name(
                str(source_event_name or ""), pd.get("Movement_Type")
            )
            event_def_id = event_def_map.get(event_name)

            timestamp_str = pd.get("Event_Timestamp")
            tz_str = pd.get("Timezone", "Africa/Johannesburg")

            parsed_tz = None
            utc_val = None
            if timestamp_str and timestamp_str != "":
                try:
                    utc_val = self.parse_datetime(timestamp_str, tz_str)
                    parsed_tz = utc_val.astimezone(pytz.timezone(tz_str)) if utc_val else None
                except Exception:
                    pass

            scope = str(pd.get("Movement_Type") or "").strip().upper()
            scope = {"INWARD": "ARRIVAL", "OUTWARD": "SAILING", "DEPARTURE": "SAILING"}.get(scope, scope)
            if scope not in {"ARRIVAL", "SHIFTING", "SAILING"}:
                scope = "ARRIVAL"
            if (
                not pd.get("Movement_Type")
                and event_name
                and ("SAILING" in event_name or "DEPARTURE" in event_name or "OUT" in event_name)
            ):
                scope = "SAILING"
            elif not pd.get("Movement_Type") and event_name and "SHIFT" in event_name:
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
                    operation_type=pd.get("Operation_Type"),
                    attributes={
                        key: value
                        for key, value in pd.items()
                        if key
                        not in {
                            "VCN",
                            "Event_Name",
                            "Event_Timestamp",
                            "Movement_Type",
                            "Operation_Type",
                            "Timezone",
                            "Source_System",
                            "Event_ID",
                            "Verification_Status",
                            "Confidence_Score",
                        }
                        and value not in {None, ""}
                    }
                    | {"source_event_name": source_event_name},
                    is_quarantined=False,
                )
                self.db.add(ev)
                event_keys_with_source.add((vc_id, event_def_id))

        batch_staging = (
            self.db.execute(select(StagingRecord).where(StagingRecord.ingestion_batch_id == batch.batch_id))
            .scalars()
            .all()
        )
        from apps.api.models.canonical import ServiceAssignment, ServiceExecution, ServiceRequest

        def dt_parse(dt_str):
            return self.parse_datetime(dt_str)

        service_records = [
            r
            for r in batch_staging
            if r.canonical_table == "service_request"
            and r.validation_status not in {"DUPLICATE", "EXCLUDED", "INVALID"}
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
            if r.canonical_table == "delay" and r.validation_status not in {"DUPLICATE", "EXCLUDED", "INVALID"}
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
            if r.canonical_table == "cargo_ops" and r.validation_status not in {"DUPLICATE", "EXCLUDED", "INVALID"}
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
                attributes={
                    key: value
                    for key, value in pd_data.items()
                    if key
                    not in {
                        "VCN",
                        "Cargo_Operation_ID",
                        "Cargo_Type",
                        "Operation_Type",
                        "Planned_Quantity",
                        "Unit",
                        "Cargo_Start",
                        "Cargo_End",
                        "Working_Hours",
                        "Resources_Deployed",
                        "Downtime_Hours",
                        "Actual_Quantity",
                        "Data_Status",
                    }
                    and value not in {None, ""}
                },
            )
            self.db.add(cg)

            # Optional FRD-v2 berth timestamps use the governed event envelope.
            # An explicit Events observation wins; CargoOps supplies the event
            # only when that call/event slot otherwise has no source.
            for event_name in self.standardization.berth_datetime_fields:
                column_name = self.standardization.BERTH_TARGET_COLUMNS.get(event_name, event_name)
                source_value = pd_data.get(column_name)
                event_time = dt_parse(source_value)
                if event_time is None:
                    continue
                event_def_id = event_def_map.get(event_name)
                if event_def_id is None:
                    definition = EventDefinition(
                        name=event_name,
                        category="Berth",
                        description=f"FRD v2 berth attribute: {event_name}",
                    )
                    self.db.add(definition)
                    self.db.flush()
                    event_def_id = definition.id
                    event_def_map[event_name] = event_def_id
                if (vc_id, event_def_id) in event_keys_with_source:
                    continue
                event_counters[(vc_id, event_def_id)] = event_counters.get((vc_id, event_def_id), 0) + 1
                self.db.add(
                    EventOccurrence(
                        source_lineage_id=f"{r.source_file_id}:{r.worksheet_name}:{r.row_number}",
                        vessel_call_id=vc_id,
                        event_definition_id=event_def_id,
                        occurrence_index=event_counters[(vc_id, event_def_id)],
                        movement_scope="ARRIVAL",
                        operation_type=pd_data.get("Operation_Type"),
                        attributes={"source_field": event_name, "source_worksheet": "CargoOps"},
                        original_string=str(source_value),
                        parsed_value=event_time,
                        source_timezone="Africa/Johannesburg",
                        utc_value=event_time,
                        capture_method="SYSTEM",
                        verification_status="Unverified",
                        source_system="CargoOps",
                        source_record_id=pd_data.get("Cargo_Operation_ID"),
                        ingestion_batch_id=batch.batch_id,
                        is_quarantined=False,
                    )
                )
                event_keys_with_source.add((vc_id, event_def_id))

            # Update vessel_call quantity_unit and quantity_value from cargo ops
            vc = self.db.query(VesselCall).filter_by(id=vc_id).first()
            if vc:
                if pd_data.get("Unit"):
                    vc.quantity_unit = pd_data.get("Unit")
                if parse_flt(pd_data.get("Actual_Quantity")) is not None:
                    vc.quantity_value = parse_flt(pd_data.get("Actual_Quantity"))

        batch.status = completion_status
        self.db.commit()
