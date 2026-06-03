from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any

from bpcl_delivery_sheet_generator.config import EnrichmentConfig
from bpcl_delivery_sheet_generator.models import (
    CashMemoExtractionRecord,
    DeliveryRecord,
    ENRICHMENT_NOT_AVAILABLE,
    ExtractionSummary,
)


class DeliveryEnricherError(Exception):
    """Raised when delivery enrichment fails."""


@dataclass(frozen=True)
class DeliveryEnrichmentResult:
    records: list[DeliveryRecord]
    audit_rows: list[dict[str, Any]]
    summary: ExtractionSummary
    warnings: list[str]


class DeliveryEnricher:
    """Enriches DeliveryRecord objects using CashMemoExtractionRecord objects."""

    _VALID_ENRICHMENT_VALUES = {"Y", "N", "NA"}

    def __init__(
        self,
        enrichment_config: EnrichmentConfig,
        logger: logging.Logger | None = None,
    ) -> None:
        self.enrichment_config = enrichment_config
        self.logger = logger or logging.getLogger(__name__)

    def enrich(
        self,
        delivery_records: list[DeliveryRecord],
        extraction_records: list[CashMemoExtractionRecord],
    ) -> DeliveryEnrichmentResult:
        self.logger.info(
            "delivery_enrichment_started | delivery_records=%d extraction_records=%d enabled=%s",
            len(delivery_records),
            len(extraction_records),
            self.enrichment_config.enabled,
        )

        if not self.enrichment_config.enabled:
            return self._build_disabled_result(delivery_records)

        if not delivery_records:
            return self._build_empty_result(extraction_records)

        if not extraction_records:
            raise DeliveryEnricherError(
                "Delivery enrichment is enabled but no cash memo extraction records were provided."
            )

        lookup, duplicate_warnings = self._build_lookup(extraction_records)

        enriched_records: list[DeliveryRecord] = []
        audit_rows: list[dict[str, Any]] = []
        warnings: list[str] = list(duplicate_warnings)

        matched_count = 0
        unmatched_count = 0
        matched_keys: set[tuple[str, str]] = set()

        for record in delivery_records:
            delivery_key = self._delivery_lookup_key(record)
            extraction = lookup.get(delivery_key)

            if extraction is None:
                unmatched_count += 1
                enriched_records.append(self._mark_missing(record))

                warning = (
                    "Missing PDF invoice for "
                    f"consumer_number={record.consumer_number}, "
                    f"cash_memo_no={record.cash_memo_no}"
                )
                warnings.append(warning)
                audit_rows.append(self._build_missing_audit_row(record))

                self.logger.warning(
                    "delivery_enrichment_match_missing | consumer_number=%s cash_memo_no=%s",
                    record.consumer_number,
                    record.cash_memo_no,
                )
                continue

            matched_count += 1
            matched_keys.add(delivery_key)

            enriched_records.append(self._apply_extraction(record, extraction))
            audit_rows.append(self._build_matched_audit_row(record, extraction))

        extraction_only_keys = set(lookup.keys()) - matched_keys

        for extraction_only_key in sorted(extraction_only_keys):
            extraction = lookup[extraction_only_key]
            warning = (
                "Extraction-only PDF invoice found: "
                f"consumer_number={extraction.consumer_number}, "
                f"invoice_no={extraction.invoice_no}"
            )
            warnings.append(warning)
            audit_rows.append(self._build_extraction_only_audit_row(extraction))

        if unmatched_count and getattr(
            self.enrichment_config, "fail_on_missing_matches", False
        ):
            raise DeliveryEnricherError(
                f"Missing PDF invoice for {unmatched_count} delivery records."
            )

        summary = self._build_summary(
            delivery_records=delivery_records,
            extraction_records=extraction_records,
            matched_records=matched_count,
            unmatched_records=unmatched_count,
            conflicting_records=0,
        )

        self.logger.info(
            "delivery_enrichment_completed | total=%d matched=%d unmatched=%d extraction_only=%d warnings=%d",
            len(delivery_records),
            matched_count,
            unmatched_count,
            len(extraction_only_keys),
            len(warnings),
        )

        return DeliveryEnrichmentResult(
            records=enriched_records,
            audit_rows=audit_rows,
            summary=summary,
            warnings=warnings,
        )

    def _build_lookup(
        self,
        extraction_records: list[CashMemoExtractionRecord],
    ) -> tuple[dict[tuple[str, str], CashMemoExtractionRecord], list[str]]:
        lookup: dict[tuple[str, str], CashMemoExtractionRecord] = {}
        warnings: list[str] = []

        for extraction in extraction_records:
            self._validate_extraction_record(extraction)
            extraction_key = self._extraction_lookup_key(extraction)

            consumer_key, invoice_key = extraction_key

            if not consumer_key:
                raise DeliveryEnricherError(
                    f"Cash memo extraction record has empty consumer number: {extraction}"
                )

            if not invoice_key:
                raise DeliveryEnricherError(
                    f"Cash memo extraction record has empty invoice number: {extraction}"
                )

            existing = lookup.get(extraction_key)

            if existing is None:
                lookup[extraction_key] = extraction
                continue

            if self._same_enrichment_values(existing, extraction):
                warning = (
                    "Duplicate same-value extraction ignored for "
                    f"consumer_number={extraction.consumer_number}, "
                    f"invoice_no={extraction.invoice_no}"
                )
                warnings.append(warning)

                self.logger.warning(
                    "delivery_enrichment_duplicate_detected | consumer_number=%s invoice_no=%s action=ignored_duplicate_same_values",
                    extraction.consumer_number,
                    extraction.invoice_no,
                )
                continue

            message = (
                "Conflicting cash memo extraction records detected for "
                f"consumer_number={extraction.consumer_number}, "
                f"invoice_no={extraction.invoice_no}"
            )

            self.logger.error(
                "delivery_enrichment_conflict_detected | consumer_number=%s invoice_no=%s existing=%s incoming=%s",
                extraction.consumer_number,
                extraction.invoice_no,
                existing,
                extraction,
            )

            if self.enrichment_config.fail_on_conflicts:
                raise DeliveryEnricherError(message)

            warnings.append(message)

        self.logger.info(
            "delivery_enrichment_lookup_built | unique_consumer_invoice_pairs=%d warnings=%d",
            len(lookup),
            len(warnings),
        )

        return lookup, warnings

    def _apply_extraction(
        self,
        record: DeliveryRecord,
        extraction: CashMemoExtractionRecord,
    ) -> DeliveryRecord:
        return replace(
            record,
            mandatory_inspection_due=extraction.mandatory_inspection_due,
            biometric_due=extraction.biometric_due,
            suraksha_tube_due=extraction.suraksha_tube_due,
            online_payment=extraction.online_payment,
        )

    def _mark_missing(self, record: DeliveryRecord) -> DeliveryRecord:
        missing_value = getattr(
            self.enrichment_config,
            "missing_match_value",
            ENRICHMENT_NOT_AVAILABLE,
        )

        if missing_value not in self._VALID_ENRICHMENT_VALUES:
            raise DeliveryEnricherError(
                f"Invalid missing_match_value={missing_value}. Allowed values are Y, N, NA."
            )

        return replace(
            record,
            mandatory_inspection_due=missing_value,
            biometric_due=missing_value,
            suraksha_tube_due=missing_value,
            online_payment=missing_value,
        )

    def _build_matched_audit_row(
        self,
        record: DeliveryRecord,
        extraction: CashMemoExtractionRecord,
    ) -> dict[str, Any]:
        return {
            "consumer_number": record.consumer_number,
            "cash_memo_no": record.cash_memo_no,
            "invoice_no": extraction.invoice_no,
            "order_no": extraction.order_no,
            "mandatory_inspection_due": extraction.mandatory_inspection_due,
            "biometric_due": extraction.biometric_due,
            "suraksha_tube_due": extraction.suraksha_tube_due,
            "online_payment": extraction.online_payment,
            "source_pdf": extraction.source_pdf,
            "source_page": extraction.source_page,
            "enrichment_status": "MATCHED",
            "remarks": "",
        }

    def _build_missing_audit_row(self, record: DeliveryRecord) -> dict[str, Any]:
        return {
            "consumer_number": record.consumer_number,
            "cash_memo_no": record.cash_memo_no,
            "invoice_no": "",
            "order_no": "",
            "mandatory_inspection_due": ENRICHMENT_NOT_AVAILABLE,
            "biometric_due": ENRICHMENT_NOT_AVAILABLE,
            "suraksha_tube_due": ENRICHMENT_NOT_AVAILABLE,
            "online_payment": ENRICHMENT_NOT_AVAILABLE,
            "source_pdf": "",
            "source_page": "",
            "enrichment_status": "MISSING_PDF_INVOICE",
            "remarks": (
                "No PDF invoice found for "
                f"ConsumerNumber={record.consumer_number}, "
                f"CashMemoNo={record.cash_memo_no}."
            ),
        }

    def _build_extraction_only_audit_row(
        self,
        extraction: CashMemoExtractionRecord,
    ) -> dict[str, Any]:
        return {
            "consumer_number": extraction.consumer_number,
            "cash_memo_no": "",
            "invoice_no": extraction.invoice_no,
            "order_no": extraction.order_no,
            "mandatory_inspection_due": extraction.mandatory_inspection_due,
            "biometric_due": extraction.biometric_due,
            "suraksha_tube_due": extraction.suraksha_tube_due,
            "online_payment": extraction.online_payment,
            "source_pdf": extraction.source_pdf,
            "source_page": extraction.source_page,
            "enrichment_status": "EXTRACTION_ONLY",
            "remarks": (
                "PDF invoice was extracted but no CSV row matched "
                "the same consumer number and invoice number."
            ),
        }

    def _build_summary(
        self,
        delivery_records: list[DeliveryRecord],
        extraction_records: list[CashMemoExtractionRecord],
        matched_records: int,
        unmatched_records: int,
        conflicting_records: int,
    ) -> ExtractionSummary:
        return ExtractionSummary(
            total_csv_records=len(delivery_records),
            total_extracted_records=len(extraction_records),
            matched_records=matched_records,
            unmatched_records=unmatched_records,
            conflicting_records=conflicting_records,
            mandatory_inspection_due_count=sum(
                1 for record in extraction_records if record.mandatory_inspection_due == "Y"
            ),
            biometric_due_count=sum(
                1 for record in extraction_records if record.biometric_due == "Y"
            ),
            suraksha_tube_due_count=sum(
                1 for record in extraction_records if record.suraksha_tube_due == "Y"
            ),
            online_payment_count=sum(
                1 for record in extraction_records if record.online_payment == "Y"
            ),
        )

    def _build_disabled_result(
        self,
        delivery_records: list[DeliveryRecord],
    ) -> DeliveryEnrichmentResult:
        summary = ExtractionSummary(
            total_csv_records=len(delivery_records),
            total_extracted_records=0,
            matched_records=0,
            unmatched_records=0,
            conflicting_records=0,
            mandatory_inspection_due_count=0,
            biometric_due_count=0,
            suraksha_tube_due_count=0,
            online_payment_count=0,
        )

        return DeliveryEnrichmentResult(
            records=delivery_records,
            audit_rows=[],
            summary=summary,
            warnings=[],
        )

    def _build_empty_result(
        self,
        extraction_records: list[CashMemoExtractionRecord],
    ) -> DeliveryEnrichmentResult:
        summary = ExtractionSummary(
            total_csv_records=0,
            total_extracted_records=len(extraction_records),
            matched_records=0,
            unmatched_records=0,
            conflicting_records=0,
            mandatory_inspection_due_count=0,
            biometric_due_count=0,
            suraksha_tube_due_count=0,
            online_payment_count=0,
        )

        return DeliveryEnrichmentResult(
            records=[],
            audit_rows=[],
            summary=summary,
            warnings=[],
        )

    def _validate_extraction_record(
        self,
        extraction: CashMemoExtractionRecord,
    ) -> None:
        values = {
            "mandatory_inspection_due": extraction.mandatory_inspection_due,
            "biometric_due": extraction.biometric_due,
            "suraksha_tube_due": extraction.suraksha_tube_due,
            "online_payment": extraction.online_payment,
        }

        invalid_values = {
            field: value
            for field, value in values.items()
            if value not in self._VALID_ENRICHMENT_VALUES
        }

        if invalid_values:
            raise DeliveryEnricherError(
                f"Invalid enrichment values detected for consumer_number={extraction.consumer_number}, "
                f"invoice_no={extraction.invoice_no}: {invalid_values}"
            )

    def _same_enrichment_values(
            self,
            left: CashMemoExtractionRecord,
            right: CashMemoExtractionRecord,
    ) -> bool:
        return (
                left.mandatory_inspection_due == right.mandatory_inspection_due
                and left.biometric_due == right.biometric_due
                and left.suraksha_tube_due == right.suraksha_tube_due
                and left.online_payment == right.online_payment
        )

    def _delivery_lookup_key(self, record: DeliveryRecord) -> tuple[str, str]:
        return (
            self._normalize_consumer_number(record.consumer_number),
            self._normalize_invoice_number(record.cash_memo_no),
        )

    def _extraction_lookup_key(
        self,
        extraction: CashMemoExtractionRecord,
    ) -> tuple[str, str]:
        return (
            self._normalize_consumer_number(extraction.consumer_number),
            self._normalize_invoice_number(extraction.invoice_no),
        )

    def _normalize_consumer_number(self, value: object) -> str:
        return self._normalize_identifier(value)

    def _normalize_invoice_number(self, value: object) -> str:
        return self._normalize_identifier(value)

    def _normalize_identifier(self, value: object) -> str:
        if value is None:
            return ""

        text = str(value).strip()

        if text.endswith(".0"):
            text = text[:-2]

        return text.replace(" ", "")