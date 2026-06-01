from __future__ import annotations

import logging
import zipfile
from dataclasses import dataclass
from pathlib import Path

from bpcl_delivery_sheet_generator.config import OutputConfig


class ZIPPackagerError(Exception):
    """Raised when ZIP package creation fails."""


@dataclass
class ZIPPackager:
    output_config: OutputConfig
    logger: logging.Logger | None = None

    PACKAGE_FILENAME = "bpcl_delivery_sheet_package.zip"

    def create_package(
        self,
        combined_pdf_path: Path | None,
        split_pdf_paths: list[Path],
        enrichment_audit_path: Path | None,
        extraction_summary_path: Path | None,
    ) -> Path | None:
        output_dir = Path(self.output_config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        package_path = output_dir / self.PACKAGE_FILENAME

        files_to_add: list[tuple[Path, str]] = []

        if combined_pdf_path is not None:
            files_to_add.append(
                (
                    self._validate_file(combined_pdf_path, "combined PDF"),
                    "delivery_sheet_all_deliverymen.pdf",
                )
            )

        for split_pdf_path in split_pdf_paths or []:
            path = self._validate_file(split_pdf_path, "split PDF")
            files_to_add.append((path, f"split_pdfs/{path.name}"))

        if enrichment_audit_path is not None:
            files_to_add.append(
                (
                    self._validate_file(enrichment_audit_path, "enrichment audit CSV"),
                    "audit/cash_memo_enrichment_audit.csv",
                )
            )

        if extraction_summary_path is not None:
            files_to_add.append(
                (
                    self._validate_file(extraction_summary_path, "extraction summary CSV"),
                    "audit/cash_memo_extraction_summary.csv",
                )
            )

        if not files_to_add:
            self._log_info("zip_package_skipped", reason="no_files_to_package")
            return None

        try:
            with zipfile.ZipFile(package_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
                for source_path, archive_name in files_to_add:
                    zip_file.write(source_path, archive_name)

            self._log_info(
                "zip_package_created",
                package_path=str(package_path),
                file_count=len(files_to_add),
            )
            return package_path

        except Exception as exc:
            self._log_error("zip_package_failed", error=str(exc))
            raise ZIPPackagerError(f"Failed to create ZIP package: {exc}") from exc

    def _validate_file(self, path: Path, label: str) -> Path:
        resolved_path = Path(path)

        if not resolved_path.exists():
            raise ZIPPackagerError(f"{label} does not exist: {resolved_path}")

        if not resolved_path.is_file():
            raise ZIPPackagerError(f"{label} is not a file: {resolved_path}")

        return resolved_path

    def _log_info(self, event: str, **metadata: object) -> None:
        if self.logger:
            self.logger.info(event, extra=metadata)

    def _log_error(self, event: str, **metadata: object) -> None:
        if self.logger:
            self.logger.error(event, extra=metadata)