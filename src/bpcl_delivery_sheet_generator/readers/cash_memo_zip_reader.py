from __future__ import annotations

import logging
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from bpcl_delivery_sheet_generator.config import (
    EnrichmentConfig,
    InputConfig,
    OutputConfig,
)


class CashMemoZIPReaderError(Exception):
    """Raised when cash memo ZIP validation or extraction fails."""


@dataclass
class CashMemoZIPReader:
    input_config: InputConfig
    output_config: OutputConfig
    enrichment_config: EnrichmentConfig
    logger: logging.Logger | None = None

    def read(self) -> list[Path]:
        self._log_info("cash_memo_zip_read_started")

        zip_path = self._validate_zip_path()

        with self._open_zip(zip_path) as zip_file:
            pdf_members = self._list_pdf_members(zip_file)
            self._validate_pdf_members(pdf_members)
            extracted_paths = self._extract_pdf_members(zip_file, pdf_members)

        self._log_info(
            "cash_memo_zip_read_completed",
            extracted_pdf_count=len(extracted_paths),
        )

        return extracted_paths

    def _log_info(self, message: str, **kwargs: object) -> None:
        if self.logger:
            self.logger.info("%s | %s", message, kwargs)

    def _validate_zip_path(self) -> Path:
        if not self.input_config.cash_memo_zip_path:
            raise CashMemoZIPReaderError("Cash memo ZIP path is required.")

        zip_path = Path(self.input_config.cash_memo_zip_path)

        if not zip_path.exists():
            raise CashMemoZIPReaderError(f"Cash memo ZIP file not found: {zip_path}")

        if not zip_path.is_file():
            raise CashMemoZIPReaderError(f"Cash memo ZIP path is not a file: {zip_path}")

        if zip_path.suffix.lower() != ".zip":
            raise CashMemoZIPReaderError(f"Cash memo file must be a .zip file: {zip_path}")

        self._log_info("cash_memo_zip_path_validated", zip_path=str(zip_path))
        return zip_path

    def _open_zip(self, zip_path: Path) -> zipfile.ZipFile:
        try:
            zip_file = zipfile.ZipFile(zip_path, mode="r")
            corrupt_member = zip_file.testzip()
        except zipfile.BadZipFile as exc:
            raise CashMemoZIPReaderError(f"Invalid or corrupt ZIP file: {zip_path}") from exc
        except OSError as exc:
            raise CashMemoZIPReaderError(f"Unable to read ZIP file: {zip_path}") from exc

        if corrupt_member:
            zip_file.close()
            raise CashMemoZIPReaderError(
                f"Corrupt file found inside ZIP: {corrupt_member}"
            )

        self._log_info("cash_memo_zip_opened", zip_path=str(zip_path))
        return zip_file

    def _list_pdf_members(self, zip_file: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
        pdf_members: list[zipfile.ZipInfo] = []
        ignored_members: list[str] = []

        for member in zip_file.infolist():
            if member.is_dir():
                continue

            member_name = member.filename

            if member_name.lower().endswith(".pdf"):
                pdf_members.append(member)
            else:
                ignored_members.append(member_name)

        if ignored_members:
            self._log_info(
                "cash_memo_zip_non_pdf_members_ignored",
                ignored_count=len(ignored_members),
                ignored_members=ignored_members,
            )

        self._log_info(
            "cash_memo_zip_pdf_members_found",
            pdf_count=len(pdf_members),
        )

        return pdf_members

    def _validate_pdf_members(self, pdf_members: list[zipfile.ZipInfo]) -> None:
        if pdf_members:
            return

        message = "Cash memo ZIP contains no PDF files."

        if self.enrichment_config.fail_on_no_pdfs:
            raise CashMemoZIPReaderError(message)

        self._log_info("cash_memo_zip_no_pdfs_found")

    def _get_work_dir(self) -> Path:
        work_dir = Path(self.output_config.output_dir) / "_work" / "cash_memo_pdfs"

        if work_dir.exists():
            shutil.rmtree(work_dir)

        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir

    def _safe_output_path(
        self,
        *,
        work_dir: Path,
        member: zipfile.ZipInfo,
        used_names: set[str],
    ) -> Path:
        original_name = Path(member.filename).name

        if not original_name:
            raise CashMemoZIPReaderError(
                f"Invalid PDF member name in ZIP: {member.filename}"
            )

        candidate_name = original_name
        stem = Path(original_name).stem
        suffix = Path(original_name).suffix

        counter = 1
        while candidate_name.lower() in used_names:
            candidate_name = f"{stem}_{counter}{suffix}"
            counter += 1

        used_names.add(candidate_name.lower())

        output_path = work_dir / candidate_name
        resolved_work_dir = work_dir.resolve()
        resolved_output_path = output_path.resolve()

        if resolved_work_dir not in resolved_output_path.parents:
            raise CashMemoZIPReaderError(
                f"Unsafe ZIP member path detected: {member.filename}"
            )

        return output_path

    def _extract_pdf_members(
        self,
        zip_file: zipfile.ZipFile,
        pdf_members: list[zipfile.ZipInfo],
    ) -> list[Path]:
        work_dir = self._get_work_dir()
        extracted_paths: list[Path] = []
        used_names: set[str] = set()

        for member in pdf_members:
            output_path = self._safe_output_path(
                work_dir=work_dir,
                member=member,
                used_names=used_names,
            )

            try:
                with zip_file.open(member, mode="r") as source:
                    output_path.write_bytes(source.read())
            except OSError as exc:
                raise CashMemoZIPReaderError(
                    f"Failed to extract PDF from ZIP: {member.filename}"
                ) from exc

            extracted_paths.append(output_path)

            self._log_info(
                "cash_memo_zip_pdf_extracted",
                member_name=member.filename,
                output_path=str(output_path),
            )

        return extracted_paths