from __future__ import annotations

import logging
from dataclasses import replace

from bpcl_delivery_sheet_generator.config import EnrichmentConfig
from bpcl_delivery_sheet_generator.models import (
    CashMemoExtractionRecord,
    DeliveryRecord,
    ENRICHMENT_NOT_AVAILABLE,
)


class DeliveryEnricherError(Exception):
    """Raised when delivery enrichment fails."""


class DeliveryEnricher:
    """
    Enriches DeliveryRecord objects using CashMemoExtractionRecord objects.
    """

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
    ) -> list[DeliveryRecord]:
        self.logger.info(
            "delivery_enrichment_started | delivery_records=%d extraction_records=%d enabled=%s",
            len(delivery_records),
            len(extraction_records),
            self.enrichment_config.enabled,
        )

        if not self.enrichment_config.enabled:
            self.logger.info("delivery_enrichment_skipped | reason=enrichment_disabled")
            return delivery_records

        if not delivery_records:
            self.logger.info("delivery_enrichment_completed | reason=no_delivery_records")
            return []

        if not extraction_records:
            raise DeliveryEnricherError(
                "Delivery enrichment is enabled but no cash memo extraction records were provided."
            )

        lookup = self._build_lookup(extraction_records)

        enriched_records: list[DeliveryRecord] = []
        matched_count = 0
        unmatched_count = 0

        for record in delivery_records:
            consumer_key = self._normalize_consumer_number(record.consumer_number)
            extraction = lookup.get(consumer_key)

            if extraction is None:
                unmatched_count += 1
                enriched_records.append(self._mark_missing(record))

                self.logger.warning(
                    "delivery_enrichment_match_missing | consumer_number=%s cash_memo_no=%s",
                    record.consumer_number,
                    record.cash_memo_no,
                )
                continue

            matched_count += 1
            enriched_records.append(self._apply_extraction(record, extraction))

            self.logger.debug(
                "delivery_enrichment_match_found | consumer_number=%s cash_memo_no=%s invoice_no=%s order_no=%s",
                record.consumer_number,
                record.cash_memo_no,
                extraction.invoice_no,
                extraction.order_no,
            )

        if unmatched_count and getattr(
            self.enrichment_config, "fail_on_missing_matches", False
        ):
            raise DeliveryEnricherError(
                f"Missing cash memo enrichment for {unmatched_count} delivery records."
            )

        self.logger.info(
            "delivery_enrichment_completed | total=%d matched=%d unmatched=%d",
            len(delivery_records),
            matched_count,
            unmatched_count,
        )

        return enriched_records

    def _build_lookup(
        self,
        extraction_records: list[CashMemoExtractionRecord],
    ) -> dict[str, CashMemoExtractionRecord]:
        lookup: dict[str, CashMemoExtractionRecord] = {}
        duplicate_same_values_count = 0

        for extraction in extraction_records:
            self._validate_extraction_record(extraction)

            consumer_key = self._normalize_consumer_number(extraction.consumer_number)

            if not consumer_key:
                raise DeliveryEnricherError(
                    f"Cash memo extraction record has empty consumer number: {extraction}"
                )

            existing = lookup.get(consumer_key)

            if existing is None:
                lookup[consumer_key] = extraction
                continue

            if self._same_enrichment_values(existing, extraction):
                duplicate_same_values_count += 1
                self.logger.warning(
                    "delivery_enrichment_duplicate_detected | consumer_number=%s invoice_no=%s action=ignored_duplicate_same_values",
                    extraction.consumer_number,
                    extraction.invoice_no,
                )
                continue

            message = (
                "Conflicting cash memo extraction records detected for "
                f"consumer_number={extraction.consumer_number}"
            )

            self.logger.error(
                "delivery_enrichment_conflict_detected | consumer_number=%s existing=%s incoming=%s",
                extraction.consumer_number,
                existing,
                extraction,
            )

            if self.enrichment_config.fail_on_conflicts:
                raise DeliveryEnricherError(message)

            self.logger.warning(
                "delivery_enrichment_conflict_ignored | consumer_number=%s action=kept_first_record",
                extraction.consumer_number,
            )

        self.logger.info(
            "delivery_enrichment_lookup_built | unique_consumers=%d duplicate_same_values=%d",
            len(lookup),
            duplicate_same_values_count,
        )

        return lookup

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
                f"Invalid missing_match_value={missing_value}. "
                "Allowed values are Y, N, NA."
            )

        return replace(
            record,
            mandatory_inspection_due=missing_value,
            biometric_due=missing_value,
            suraksha_tube_due=missing_value,
            online_payment=missing_value,
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
                f"Invalid enrichment values detected for consumer_number={extraction.consumer_number}: "
                f"{invalid_values}"
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

    def _normalize_consumer_number(self, value: object) -> str:
        if value is None:
            return ""

        text = str(value).strip()

        if text.endswith(".0"):
            text = text[:-2]

        return text.replace(" ", "")