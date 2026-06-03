from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


ENRICHMENT_YES = "Y"
ENRICHMENT_NO = "N"
ENRICHMENT_NOT_AVAILABLE = "NA"

AUDIT_STATUS_MATCHED = "MATCHED"
AUDIT_STATUS_MISSING_PDF_INVOICE = "MISSING_PDF_INVOICE"
AUDIT_STATUS_EXTRACTION_ONLY = "EXTRACTION_ONLY"

@dataclass(frozen=True)
class DeliveryRecord:
    area: str
    operator_name: str
    booking_date: str
    cash_memo_date: str
    cash_memo_no: str
    consumer_number: str
    consumer_name: str
    address1: str
    address2: str
    address3: str
    mobile_number: str

    mandatory_inspection_due: str = ENRICHMENT_NOT_AVAILABLE
    biometric_due: str = ENRICHMENT_NOT_AVAILABLE
    suraksha_tube_due: str = ENRICHMENT_NOT_AVAILABLE
    online_payment: str = ENRICHMENT_NOT_AVAILABLE


@dataclass(frozen=True)
class DeliveryBatch:
    operator_name: str
    records: tuple[DeliveryRecord, ...]


@dataclass(frozen=True)
class CashMemoExtractionRecord:
    consumer_number: str
    invoice_no: str
    order_no: str

    mandatory_inspection_due: str
    biometric_due: str
    suraksha_tube_due: str
    online_payment: str

    source_pdf: str
    source_page: int


@dataclass(frozen=True)
class ExtractionSummary:
    total_csv_records: int
    total_extracted_records: int
    matched_records: int
    unmatched_records: int
    conflicting_records: int

    mandatory_inspection_due_count: int
    biometric_due_count: int
    suraksha_tube_due_count: int
    online_payment_count: int


@dataclass(frozen=True)
class GenerationResult:
    total_input_rows: int
    total_output_rows: int
    total_batches: int

    combined_pdf_path: Path | None = None
    split_pdf_paths: tuple[Path, ...] = field(default_factory=tuple)
    zip_path: Path | None = None

    warnings: tuple[str, ...] = field(default_factory=tuple)

    enrichment_audit_path: Path | None = None
    extraction_summary_path: Path | None = None