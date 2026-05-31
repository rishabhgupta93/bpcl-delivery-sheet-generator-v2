from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


GenerationMode = Literal["combined", "split", "both"]
ColumnAlign = Literal["left", "center", "right"]
PageOrientation = Literal["portrait", "landscape"]


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
    width_weight: float
    align: ColumnAlign = "left"
    header_bold: bool = False
    value_bold: bool = False
    blank_display_value: str = ""
    source_field: str | None = None


@dataclass(frozen=True)
class PdfLayoutConfig:
    page_size: str = "A4"
    orientation: PageOrientation = "landscape"
    title: str = "Venkateshwar Gas Service - Delivery Handover Sheet"
    show_operator_in_header: bool = True
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
        PdfColumnConfig("serial_no", "S.No", 0.7, "center"),
        PdfColumnConfig("cash_memo_no", "Memo No", 1.2, "center"),
        PdfColumnConfig("consumer_number", "Consumer No", 1.4, "center"),
        PdfColumnConfig("consumer_name", "Consumer Name", 2.2),
        PdfColumnConfig("area", "Area", 1.7),
        PdfColumnConfig("booking_date", "Booking", 1.2, "center"),
        PdfColumnConfig("cash_memo_date", "Memo Date", 1.3, "center"),
        PdfColumnConfig("address", "Address", 4.0),
        PdfColumnConfig("mobile_number", "Mobile", 1.4, "center"),
        PdfColumnConfig(
            key="mandatory_inspection_due",
            label="MI",
            width_weight=0.6,
            align="center",
            header_bold=True,
            value_bold=True,
            blank_display_value="-",
        ),
        PdfColumnConfig(
            key="biometric_due",
            label="Bio",
            width_weight=0.7,
            align="center",
            header_bold=True,
            value_bold=True,
            blank_display_value="-",
        ),
        PdfColumnConfig(
            key="suraksha_tube_due",
            label="Tube",
            width_weight=0.8,
            align="center",
            header_bold=True,
            value_bold=True,
            blank_display_value="-",
        ),
        PdfColumnConfig(
            key="online_payment",
            label="Online",
            width_weight=0.9,
            align="center",
            header_bold=True,
            value_bold=True,
            blank_display_value="-",
        ),
        PdfColumnConfig("otp", "OTP", 1.2, "center"),
        PdfColumnConfig("signature", "Signature", 2.0, "center"),
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
        self._validate_input()
        self._validate_output()
        self._validate_csv()
        self._validate_generation()
        self._validate_enrichment()
        self._validate_pdf()
        self._validate_audit()
        self._validate_logging()

    def _validate_input(self) -> None:
        if not self.input.csv_path:
            raise ValueError("input.csv_path is required")

    def _validate_output(self) -> None:
        if not self.output.output_dir:
            raise ValueError("output.output_dir is required")

    def _validate_csv(self) -> None:
        if self.csv.skip_rows < 0:
            raise ValueError("csv.skip_rows cannot be negative")

        if not self.csv.encoding:
            raise ValueError("csv.encoding is required")

        if not self.csv.required_columns:
            raise ValueError("csv.required_columns cannot be empty")

        if not self.csv.column_mapping:
            raise ValueError("csv.column_mapping cannot be empty")

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

    def _validate_generation(self) -> None:
        if self.generation.mode not in ("combined", "split", "both"):
            raise ValueError(
                "generation.mode must be one of: combined, split, both"
            )

        if not self.generation.group_by:
            raise ValueError("generation.group_by is required")

        if not self.generation.sort_by:
            raise ValueError("generation.sort_by cannot be empty")

    def _validate_enrichment(self) -> None:
        if not self.enrichment.missing_match_value:
            raise ValueError("enrichment.missing_match_value is required")

        if self.enrichment.enabled and not self.input.cash_memo_zip_path:
            raise ValueError(
                "input.cash_memo_zip_path is required when enrichment.enabled is True"
            )

    def _validate_pdf(self) -> None:
        if not self.pdf.page_size:
            raise ValueError("pdf.page_size is required")

        if self.pdf.orientation not in ("portrait", "landscape"):
            raise ValueError("pdf.orientation must be one of: portrait, landscape")

        if not self.pdf.title:
            raise ValueError("pdf.title is required")

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
            self._validate_pdf_column(column)

    @staticmethod
    def _validate_pdf_column(column: PdfColumnConfig) -> None:
        if not column.key:
            raise ValueError("pdf column key cannot be empty")

        if not column.label:
            raise ValueError(f"pdf column '{column.key}' label cannot be empty")

        if column.width_weight <= 0:
            raise ValueError(
                f"pdf column '{column.key}' must have positive width_weight"
            )

        if column.align not in ("left", "center", "right"):
            raise ValueError(
                f"pdf column '{column.key}' align must be one of: "
                "left, center, right"
            )

    def _validate_audit(self) -> None:
        if self.audit.enabled and not (
            self.audit.write_enrichment_audit
            or self.audit.write_extraction_summary
        ):
            raise ValueError(
                "audit.enabled is True but no audit outputs are enabled"
            )

        if self.audit.write_enrichment_audit and not self.audit.enrichment_audit_filename:
            raise ValueError("audit.enrichment_audit_filename is required")

        if self.audit.write_extraction_summary and not self.audit.extraction_summary_filename:
            raise ValueError("audit.extraction_summary_filename is required")

    def _validate_logging(self) -> None:
        allowed_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

        if self.logging.log_level.upper() not in allowed_log_levels:
            raise ValueError(
                "logging.log_level must be one of: "
                + ", ".join(sorted(allowed_log_levels))
            )