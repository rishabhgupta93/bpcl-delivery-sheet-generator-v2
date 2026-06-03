from __future__ import annotations

import pytest

from bpcl_delivery_sheet_generator.config import EnrichmentConfig
from bpcl_delivery_sheet_generator.enrichers import (
    DeliveryEnricher,
    DeliveryEnricherError,
)
from bpcl_delivery_sheet_generator.models import (
    CashMemoExtractionRecord,
    DeliveryRecord,
)


def _delivery_record(
    consumer_number: str = "96076255",
    cash_memo_no: str = "29218",
) -> DeliveryRecord:
    return DeliveryRecord(
        area="A",
        operator_name="OP1",
        booking_date="2026-05-31",
        cash_memo_date="2026-05-31",
        cash_memo_no=cash_memo_no,
        consumer_number=consumer_number,
        consumer_name="Test User",
        address1="Addr1",
        address2="",
        address3="",
        mobile_number="9999999999",
    )


def _extraction_record(
    consumer_number: str = "96076255",
    invoice_no: str = "29218",
    order_no: str = "22513",
    mandatory_inspection_due: str = "Y",
    biometric_due: str = "N",
    suraksha_tube_due: str = "Y",
    online_payment: str = "Y",
) -> CashMemoExtractionRecord:
    return CashMemoExtractionRecord(
        consumer_number=consumer_number,
        invoice_no=invoice_no,
        order_no=order_no,
        mandatory_inspection_due=mandatory_inspection_due,
        biometric_due=biometric_due,
        suraksha_tube_due=suraksha_tube_due,
        online_payment=online_payment,
        source_pdf="memo.pdf",
        source_page=1,
    )


def test_enrich_exact_consumer_and_invoice_match_populates_enrichment_fields() -> None:
    records = [_delivery_record(consumer_number="96076255", cash_memo_no="29218")]
    extraction_records = [
        _extraction_record(consumer_number="96076255", invoice_no="29218")
    ]

    result = DeliveryEnricher(
        EnrichmentConfig(enabled=True)
    ).enrich(records, extraction_records)

    assert len(result.records) == 1
    assert result.records[0].mandatory_inspection_due == "Y"
    assert result.records[0].biometric_due == "N"
    assert result.records[0].suraksha_tube_due == "Y"
    assert result.records[0].online_payment == "Y"

    assert len(result.audit_rows) == 1
    assert result.audit_rows[0]["enrichment_status"] == "MATCHED"
    assert result.audit_rows[0]["cash_memo_no"] == "29218"
    assert result.audit_rows[0]["invoice_no"] == "29218"

    assert result.summary.total_csv_records == 1
    assert result.summary.total_extracted_records == 1
    assert result.summary.matched_records == 1
    assert result.summary.unmatched_records == 0
    assert result.warnings == []


def test_enrich_same_consumer_different_invoice_does_not_match() -> None:
    records = [_delivery_record(consumer_number="96076255", cash_memo_no="29218")]
    extraction_records = [
        _extraction_record(consumer_number="96076255", invoice_no="29219")
    ]

    result = DeliveryEnricher(
        EnrichmentConfig(enabled=True)
    ).enrich(records, extraction_records)

    assert len(result.records) == 1
    assert result.records[0].mandatory_inspection_due == "NA"
    assert result.records[0].biometric_due == "NA"
    assert result.records[0].suraksha_tube_due == "NA"
    assert result.records[0].online_payment == "NA"

    assert result.summary.total_csv_records == 1
    assert result.summary.total_extracted_records == 1
    assert result.summary.matched_records == 0
    assert result.summary.unmatched_records == 1

    statuses = [row["enrichment_status"] for row in result.audit_rows]
    assert "MISSING_PDF_INVOICE" in statuses
    assert "EXTRACTION_ONLY" in statuses
    assert len(result.warnings) == 2


def test_enrich_same_invoice_different_consumer_does_not_match() -> None:
    records = [_delivery_record(consumer_number="11111111", cash_memo_no="29218")]
    extraction_records = [
        _extraction_record(consumer_number="96076255", invoice_no="29218")
    ]

    result = DeliveryEnricher(
        EnrichmentConfig(enabled=True)
    ).enrich(records, extraction_records)

    assert len(result.records) == 1
    assert result.records[0].mandatory_inspection_due == "NA"
    assert result.records[0].biometric_due == "NA"
    assert result.records[0].suraksha_tube_due == "NA"
    assert result.records[0].online_payment == "NA"

    assert result.summary.matched_records == 0
    assert result.summary.unmatched_records == 1

    statuses = [row["enrichment_status"] for row in result.audit_rows]
    assert "MISSING_PDF_INVOICE" in statuses
    assert "EXTRACTION_ONLY" in statuses


def test_enrich_missing_pdf_invoice_sets_na_values_and_audit_status() -> None:
    records = [_delivery_record(consumer_number="11111111", cash_memo_no="99999")]
    extraction_records = [
        _extraction_record(consumer_number="96076255", invoice_no="29218")
    ]

    result = DeliveryEnricher(
        EnrichmentConfig(enabled=True)
    ).enrich(records, extraction_records)

    assert len(result.records) == 1
    assert result.records[0].mandatory_inspection_due == "NA"
    assert result.records[0].biometric_due == "NA"
    assert result.records[0].suraksha_tube_due == "NA"
    assert result.records[0].online_payment == "NA"

    missing_rows = [
        row
        for row in result.audit_rows
        if row["enrichment_status"] == "MISSING_PDF_INVOICE"
    ]

    assert len(missing_rows) == 1
    assert missing_rows[0]["consumer_number"] == "11111111"
    assert missing_rows[0]["cash_memo_no"] == "99999"
    assert "No PDF invoice found" in missing_rows[0]["remarks"]

    assert result.summary.total_csv_records == 1
    assert result.summary.total_extracted_records == 1
    assert result.summary.matched_records == 0
    assert result.summary.unmatched_records == 1
    assert len(result.warnings) == 2


def test_enrich_duplicate_same_consumer_and_invoice_same_values_does_not_fail() -> None:
    records = [_delivery_record(consumer_number="96076255", cash_memo_no="29218")]
    extraction_records = [
        _extraction_record(consumer_number="96076255", invoice_no="29218"),
        _extraction_record(consumer_number="96076255", invoice_no="29218"),
    ]

    result = DeliveryEnricher(
        EnrichmentConfig(enabled=True)
    ).enrich(records, extraction_records)

    assert len(result.records) == 1
    assert result.records[0].mandatory_inspection_due == "Y"
    assert result.records[0].biometric_due == "N"
    assert result.records[0].suraksha_tube_due == "Y"
    assert result.records[0].online_payment == "Y"

    assert result.summary.matched_records == 1
    assert result.summary.unmatched_records == 0
    assert len(result.warnings) == 1
    assert "Duplicate same-value extraction ignored" in result.warnings[0]


def test_enrich_same_consumer_different_invoice_different_values_does_not_conflict() -> None:
    records = [_delivery_record(consumer_number="96076255", cash_memo_no="29218")]
    extraction_records = [
        _extraction_record(
            consumer_number="96076255",
            invoice_no="29218",
            mandatory_inspection_due="Y",
        ),
        _extraction_record(
            consumer_number="96076255",
            invoice_no="29219",
            mandatory_inspection_due="N",
        ),
    ]

    result = DeliveryEnricher(
        EnrichmentConfig(enabled=True)
    ).enrich(records, extraction_records)

    assert result.records[0].mandatory_inspection_due == "Y"
    assert result.summary.matched_records == 1
    assert result.summary.unmatched_records == 0

    statuses = [row["enrichment_status"] for row in result.audit_rows]
    assert "MATCHED" in statuses
    assert "EXTRACTION_ONLY" in statuses


def test_enrich_conflicting_values_for_same_consumer_and_invoice_raises_error() -> None:
    records = [_delivery_record(consumer_number="96076255", cash_memo_no="29218")]
    extraction_records = [
        _extraction_record(
            consumer_number="96076255",
            invoice_no="29218",
            mandatory_inspection_due="Y",
        ),
        _extraction_record(
            consumer_number="96076255",
            invoice_no="29218",
            mandatory_inspection_due="N",
        ),
    ]

    with pytest.raises(DeliveryEnricherError):
        DeliveryEnricher(
            EnrichmentConfig(enabled=True)
        ).enrich(records, extraction_records)


def test_enrich_consumer_number_and_invoice_normalization_handles_decimal_artifact() -> None:
    records = [_delivery_record(consumer_number="96076255.0", cash_memo_no="29218.0")]
    extraction_records = [
        _extraction_record(consumer_number="96076255", invoice_no="29218")
    ]

    result = DeliveryEnricher(
        EnrichmentConfig(enabled=True)
    ).enrich(records, extraction_records)

    assert len(result.records) == 1
    assert result.records[0].mandatory_inspection_due == "Y"
    assert result.records[0].online_payment == "Y"
    assert result.summary.matched_records == 1
    assert result.warnings == []


def test_enrich_disabled_returns_original_records() -> None:
    records = [_delivery_record()]
    extraction_records = [_extraction_record()]

    result = DeliveryEnricher(
        EnrichmentConfig(enabled=False)
    ).enrich(records, extraction_records)

    assert result.records == records
    assert result.audit_rows == []
    assert result.warnings == []
    assert result.summary.total_csv_records == 1
    assert result.summary.total_extracted_records == 0
    assert result.summary.matched_records == 0