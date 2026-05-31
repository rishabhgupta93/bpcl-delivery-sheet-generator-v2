from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


GenerationMode = Literal["combined", "split", "both"]
ColumnAlign = Literal["left", "center", "right"]


DEFAULT_SOURCE_COLUMN_MAPPING: dict[str, str] = {
    "AreaDescription": "area",
    "eKYCOperatorName": "operator_name",
    "BookDate": "booking_date",
    "CashMemoDate": "cash_memo_date",
    "CashMemoNo": "cash_memo_no",
    "ConsumerNumber": "consumer_number",
    "ConsumerName": "consumer_name",
    "Address1": "address1",
    "Address2": "address2",
    "Address3": "address3",
    "MobileNumber": "mobile_number",
}

DEFAULT_REQUIRED_COLUMNS: tuple[str, ...] = tuple(DEFAULT_SOURCE_COLUMN_MAPPING.keys())


@dataclass(frozen=True)
class InputConfig:
    csv_path: Path
    cash_memo_zip_path: Path | None = None


@dataclass(frozen=True)
class OutputConfig:
    output_dir: Path
    create_output_dir: bool = True


@dataclass(frozen=True)
class CsvConfig:
    skip_rows: int = 3
    encoding: str = "utf-8-sig"
    required_columns: tuple[str, ...] = DEFAULT_REQUIRED_COLUMNS
    column_mapping: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_SOURCE_COLUMN_MAPPING)
    )


@dataclass(frozen=True)
class GenerationConfig:
    mode: GenerationMode = "both"
    create_zip: bool = True
    group_by: str = "operator_name"
    sort_by: tuple[str, ...] = ("operator_name", "cash_memo_no")


@dataclass(frozen=True)
class EnrichmentConfig:
    enabled: bool = False
    missing_match_value: str = "NA"
    fail_on_no_pdfs: bool = True
    fail_on_no_extracted_records: bool = True
    fail_on_conflicts: bool = True


@dataclass(frozen=True)
class PdfColumnConfig:
    key: str
    label: str
    width: float
    align: ColumnAlign = "left"
    header_bold: bool = False
    value_bold: bool = False
    blank_display_value: str = ""
    source_field: str | None = None


@dataclass(frozen=True)
class PdfLayoutConfig:
    page_size: str = "A4"
    orientation: str = "landscape"
    title: str = "Venkateshwar Gas Service - Delivery Handover Sheet"
    show_operator_in_header: bool = True
    show_operator_column: bool = False
    columns: tuple[PdfColumnConfig, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class AuditConfig:
    enabled: bool = True
    write_enrichment_audit: bool = True
    write_extraction_summary: bool = True
    enrichment_audit_filename: str = "cash_memo_enrichment_audit.csv"
    extraction_summary_filename: str = "cash_memo_extraction_summary.csv"


@dataclass(frozen=True)
class LoggingConfig:
    log_level: str = "INFO"
    structured_events: bool = True


def default_v2_pdf_columns() -> tuple[PdfColumnConfig, ...]:
    return (
        PdfColumnConfig("serial_no", "S.No", 24, "center"),
        PdfColumnConfig("cash_memo_no", "Memo No", 48, "center"),
        PdfColumnConfig("consumer_number", "Consumer No", 58, "center"),
        PdfColumnConfig("consumer_name", "Consumer Name", 90),
        PdfColumnConfig("area", "Area", 70),
        PdfColumnConfig("booking_date", "Booking", 50, "center"),
        PdfColumnConfig("cash_memo_date", "Memo Date", 55, "center"),
        PdfColumnConfig("address", "Address", 150),
        PdfColumnConfig("mobile_number", "Mobile", 60, "center"),
        PdfColumnConfig(
            key="mandatory_inspection_due",
            label="MI",
            width=26,
            align="center",
            header_bold=True,
            value_bold=True,
            blank_display_value="-",
        ),
        PdfColumnConfig(
            key="biometric_due",
            label="Bio",
            width=28,
            align="center",
            header_bold=True,
            value_bold=True,
            blank_display_value="-",
        ),
        PdfColumnConfig(
            key="suraksha_tube_due",
            label="Tube",
            width=34,
            align="center",
            header_bold=True,
            value_bold=True,
            blank_display_value="-",
        ),
        PdfColumnConfig(
            key="online_payment",
            label="Online",
            width=42,
            align="center",
            header_bold=True,
            value_bold=True,
            blank_display_value="-",
        ),
        PdfColumnConfig("otp", "OTP", 55, "center"),
        PdfColumnConfig("signature", "Signature", 85, "center"),
    )


@dataclass(frozen=True)
class PackageConfig:
    input: InputConfig
    output: OutputConfig
    csv: CsvConfig = field(default_factory=CsvConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    enrichment: EnrichmentConfig = field(default_factory=EnrichmentConfig)
    pdf: PdfLayoutConfig = field(
        default_factory=lambda: PdfLayoutConfig(columns=default_v2_pdf_columns())
    )
    audit: AuditConfig = field(default_factory=AuditConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    @classmethod
    def default(
        cls,
        *,
        csv_path: str | Path,
        output_dir: str | Path,
        cash_memo_zip_path: str | Path | None = None,
    ) -> "PackageConfig":
        return cls(
            input=InputConfig(
                csv_path=Path(csv_path),
                cash_memo_zip_path=(
                    Path(cash_memo_zip_path)
                    if cash_memo_zip_path is not None
                    else None
                ),
            ),
            output=OutputConfig(output_dir=Path(output_dir)),
        )

    def validate(self) -> None:
        if not self.input.csv_path:
            raise ValueError("input.csv_path is required")

        if not self.output.output_dir:
            raise ValueError("output.output_dir is required")

        if self.generation.mode not in ("combined", "split", "both"):
            raise ValueError(
                "generation.mode must be one of: combined, split, both"
            )

        if self.csv.skip_rows < 0:
            raise ValueError("csv.skip_rows cannot be negative")

        if not self.csv.required_columns:
            raise ValueError("csv.required_columns cannot be empty")

        missing_mappings = [
            column
            for column in self.csv.required_columns
            if column not in self.csv.column_mapping
        ]

        if missing_mappings:
            raise ValueError(
                "csv.column_mapping is missing required source columns: "
                + ", ".join(missing_mappings)
            )

        if not self.generation.group_by:
            raise ValueError("generation.group_by is required")

        if not self.generation.sort_by:
            raise ValueError("generation.sort_by cannot be empty")

        if not self.pdf.columns:
            raise ValueError("pdf.columns cannot be empty")

        column_keys = [column.key for column in self.pdf.columns]
        duplicate_keys = sorted(
            {key for key in column_keys if column_keys.count(key) > 1}
        )

        if duplicate_keys:
            raise ValueError(
                "pdf.columns contains duplicate column keys: "
                + ", ".join(duplicate_keys)
            )

        for column in self.pdf.columns:
            if not column.key:
                raise ValueError("pdf column key cannot be empty")

            if not column.label:
                raise ValueError(f"pdf column '{column.key}' label cannot be empty")

            if column.width <= 0:
                raise ValueError(
                    f"pdf column '{column.key}' must have positive width"
                )

            if column.align not in ("left", "center", "right"):
                raise ValueError(
                    f"pdf column '{column.key}' align must be one of: "
                    "left, center, right"
                )

        if self.pdf.show_operator_column:
            raise ValueError(
                "pdf.show_operator_column must remain False for V2 layout. "
                "Operator should be displayed in the header only."
            )

        if self.enrichment.enabled and not self.input.cash_memo_zip_path:
            raise ValueError(
                "cash_memo_zip_path is required when enrichment.enabled is True"
            )