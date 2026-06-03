from __future__ import annotations

import csv
import logging
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable

from bpcl_delivery_sheet_generator.config import AuditConfig, OutputConfig


class AuditWriterError(Exception):
    """Raised when audit file writing fails."""


class AuditWriter:
    ENRICHMENT_AUDIT_FILENAME = "cash_memo_enrichment_audit.csv"
    EXTRACTION_SUMMARY_FILENAME = "cash_memo_extraction_summary.csv"

    def __init__(
        self,
        output_config: OutputConfig,
        audit_config: AuditConfig,
        logger: logging.Logger | None = None,
    ) -> None:
        self.output_config = output_config
        self.audit_config = audit_config
        self.logger = logger or logging.getLogger(__name__)

    def write_enrichment_audit(self, audit_rows: Iterable[Any]) -> Path | None:
        if not self.audit_config.enabled:
            return None

        rows = [self._to_dict(row) for row in audit_rows]

        if not rows:
            self.logger.info("audit_enrichment_skipped_empty")
            return None

        audit_dir = self._prepare_audit_dir()
        output_path = audit_dir / self.ENRICHMENT_AUDIT_FILENAME

        self._write_dict_rows(output_path, rows)

        self.logger.info(
            "audit_enrichment_written",
            extra={"path": str(output_path), "row_count": len(rows)},
        )
        return output_path

    def write_extraction_summary(self, summary: Any) -> Path | None:
        if not self.audit_config.enabled:
            return None

        row = self._to_dict(summary)

        audit_dir = self._prepare_audit_dir()
        output_path = audit_dir / self.EXTRACTION_SUMMARY_FILENAME

        self._write_dict_rows(output_path, [row])

        self.logger.info(
            "audit_extraction_summary_written",
            extra={"path": str(output_path)},
        )
        return output_path

    def _prepare_audit_dir(self) -> Path:
        audit_dir = Path(self.output_config.output_dir) / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        return audit_dir

    def _to_dict(self, value: Any) -> dict[str, Any]:
        if is_dataclass(value):
            return asdict(value)

        if isinstance(value, dict):
            return dict(value)

        raise AuditWriterError(
            f"Unsupported audit row type: {type(value).__name__}. "
            "Expected dataclass instance or dict."
        )

    def _write_dict_rows(self, output_path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return

        fieldnames = list(rows[0].keys())
        self._validate_consistent_schema(rows, fieldnames)

        try:
            with output_path.open("w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        except OSError as exc:
            raise AuditWriterError(
                f"Failed to write audit file: {output_path}"
            ) from exc

    def _validate_consistent_schema(
        self,
        rows: list[dict[str, Any]],
        fieldnames: list[str],
    ) -> None:
        expected_fields = set(fieldnames)

        for index, row in enumerate(rows, start=1):
            actual_fields = set(row.keys())

            if actual_fields != expected_fields:
                missing_fields = sorted(expected_fields - actual_fields)
                extra_fields = sorted(actual_fields - expected_fields)

                raise AuditWriterError(
                    "Inconsistent audit row schema detected at row "
                    f"{index}. Missing fields={missing_fields}, extra fields={extra_fields}"
                )