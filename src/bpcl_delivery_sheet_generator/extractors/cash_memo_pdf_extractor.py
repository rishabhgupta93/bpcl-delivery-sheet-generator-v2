from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from bpcl_delivery_sheet_generator.models import CashMemoExtractionRecord


class CashMemoPDFExtractorError(Exception):
    """Raised when cash memo PDF extraction validation or processing fails."""


@dataclass
class CashMemoPDFExtractor:
    logger: logging.Logger | None = None

    def extract(self, pdf_paths: list[Path]) -> list[CashMemoExtractionRecord]:
        self._validate_pdf_paths(pdf_paths)

        self._log_info(
            "cash_memo_pdf_extraction_started | pdf_count=%d",
            len(pdf_paths),
        )

        all_records: list[CashMemoExtractionRecord] = []

        for pdf_path in pdf_paths:
            path = Path(pdf_path)
            odd_pages = self._extract_odd_page_texts(path)

            self._log_info(
                "cash_memo_pdf_odd_pages_extracted | pdf=%s | odd_pages=%d",
                path.name,
                len(odd_pages),
            )

            total_blocks = 0

            for page_number, page_text in odd_pages:
                blocks = self._detect_invoice_blocks(page_text)
                total_blocks += len(blocks)

                for block in blocks:
                    record = self._parse_invoice_block(
                        block=block,
                        source_pdf=path.name,
                        source_page=page_number,
                    )
                    all_records.append(record)

            self._log_info(
                "cash_memo_pdf_invoice_blocks_detected | pdf=%s | blocks=%d",
                path.name,
                total_blocks,
            )

        if not all_records:
            raise CashMemoPDFExtractorError("No cash memo extraction records found.")

        deduped_records = self._deduplicate_records(all_records)

        self._log_info(
            "cash_memo_pdf_extraction_completed | raw_records=%d | deduped_records=%d",
            len(all_records),
            len(deduped_records),
        )

        return deduped_records

    def _validate_pdf_paths(self, pdf_paths: list[Path]) -> None:
        if not pdf_paths:
            raise CashMemoPDFExtractorError("No cash memo PDF paths provided.")

        for pdf_path in pdf_paths:
            path = Path(pdf_path)

            if not path.exists():
                raise CashMemoPDFExtractorError(f"Cash memo PDF file not found: {path}")

            if not path.is_file():
                raise CashMemoPDFExtractorError(f"Cash memo PDF path is not a file: {path}")

            if path.suffix.lower() != ".pdf":
                raise CashMemoPDFExtractorError(f"Cash memo file is not a PDF: {path}")

    def _extract_odd_page_texts(self, pdf_path: Path) -> list[tuple[int, str]]:
        try:
            reader = PdfReader(str(pdf_path))
        except Exception as exc:
            raise CashMemoPDFExtractorError(f"Failed to open PDF: {pdf_path}") from exc

        odd_pages: list[tuple[int, str]] = []

        for page_index, page in enumerate(reader.pages):
            page_number = page_index + 1

            if page_number % 2 == 0:
                self._log_info(
                    "cash_memo_pdf_page_skipped | pdf=%s | page=%d",
                    pdf_path.name,
                    page_number,
                )
                continue

            try:
                text = page.extract_text() or ""
            except Exception as exc:
                raise CashMemoPDFExtractorError(
                    f"Failed to extract text from PDF page: {pdf_path}, page={page_number}"
                ) from exc

            odd_pages.append((page_number, text))

        return odd_pages

    def _detect_invoice_blocks(self, page_text: str) -> list[str]:
        if not page_text.strip():
            return []

        parts = page_text.split("GST INVOICE")
        invoice_blocks: list[str] = []

        for part in parts[1:]:
            block = f"GST INVOICE{part}".strip()

            if "CONSNO" not in block:
                continue

            invoice_blocks.append(block)

        return invoice_blocks

    def _parse_invoice_block(
        self,
        block: str,
        source_pdf: str,
        source_page: int,
    ) -> CashMemoExtractionRecord:
        order_no = self._extract_field(r"ORNo\s*:\s*(\d+)", block, "order_no")
        invoice_no = self._extract_field(r"INVNo\s*:\s*(\d+)", block, "invoice_no")
        consumer_number = self._extract_field(
            r"CONSNO\s*:\s*(\d+)",
            block,
            "consumer_number",
        )

        due_match = re.search(
            (
                r"DUE\s*:\s*"
                r"Mand\s+Insp-(Y|N|NA)\s*,\s*"
                r"Bio-(Y|N|NA)\s*,\s*"
                r"SurTube-(Y|N|NA)"
            ),
            block,
            flags=re.IGNORECASE,
        )

        if not due_match:
            raise CashMemoPDFExtractorError("Missing or invalid DUE flags.")

        return CashMemoExtractionRecord(
            consumer_number=consumer_number,
            invoice_no=invoice_no,
            order_no=order_no,
            mandatory_inspection_due=due_match.group(1).upper(),
            biometric_due=due_match.group(2).upper(),
            suraksha_tube_due=due_match.group(3).upper(),
            online_payment=self._detect_online_payment(block),
            source_pdf=source_pdf,
            source_page=source_page,
        )

    def _deduplicate_records(
        self,
        records: list[CashMemoExtractionRecord],
    ) -> list[CashMemoExtractionRecord]:
        deduped: dict[tuple[str, str], CashMemoExtractionRecord] = {}

        for record in records:
            key = (record.consumer_number, record.invoice_no)

            if key not in deduped:
                deduped[key] = record
                continue

            existing = deduped[key]

            if self._has_same_business_values(existing, record):
                self._log_info(
                    "cash_memo_pdf_duplicate_removed | consumer_number=%s | invoice_no=%s",
                    record.consumer_number,
                    record.invoice_no,
                )
                continue

            raise CashMemoPDFExtractorError(
                "Conflicting duplicate cash memo record found for "
                f"consumer_number={record.consumer_number}, invoice_no={record.invoice_no}"
            )

        return list(deduped.values())

    def _has_same_business_values(
        self,
        left: CashMemoExtractionRecord,
        right: CashMemoExtractionRecord,
    ) -> bool:
        return (
            left.consumer_number == right.consumer_number
            and left.invoice_no == right.invoice_no
            and left.order_no == right.order_no
            and left.mandatory_inspection_due == right.mandatory_inspection_due
            and left.biometric_due == right.biometric_due
            and left.suraksha_tube_due == right.suraksha_tube_due
            and left.online_payment == right.online_payment
        )

    def _detect_online_payment(self, block: str) -> str:
        has_advance_payment = re.search(
            r"ADVANCE\s+PMT",
            block,
            flags=re.IGNORECASE,
        )

        # net_match = re.search(
        #     r"NET\s*=\s*Rs\.\s*([0-9]+(?:\.[0-9]{1,2})?)",
        #     block,
        #     flags=re.IGNORECASE | re.DOTALL,
        # )

        # if not has_advance_payment or not net_match:
        if not has_advance_payment:
            return "N"
        else:
            return "Y"

        # return "Y" if float(net_match.group(1)) == 0.0 else "N"

    def _extract_field(self, pattern: str, text: str, field_name: str) -> str:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)

        if not match:
            raise CashMemoPDFExtractorError(f"Missing required field: {field_name}")

        return match.group(1).strip()

    def _log_info(self, message: str, *args: object) -> None:
        if self.logger:
            self.logger.info(message, *args)