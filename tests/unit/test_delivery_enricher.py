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


def _delivery_record(consumer_number: str = "96076255") -> DeliveryRecord:
    return DeliveryRecord(
        area="A",
        operator_name="OP1",
        booking_date="2026-05-31",
        cash_memo_date="2026-05-31",
        cash_memo_no="001",
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


def test_enrich_matched_consumer_populates_enrichment_fields() -> None:
    records = [_delivery_record()]
    extraction_records = [_extraction_record()]

    enriched = DeliveryEnricher(
        EnrichmentConfig(enabled=True)
    ).enrich(records, extraction_records)

    assert len(enriched) == 1
    assert enriched[0].mandatory_inspection_due == "Y"
    assert enriched[0].biometric_due == "N"
    assert enriched[0].suraksha_tube_due == "Y"
    assert enriched[0].online_payment == "Y"


def test_enrich_missing_consumer_sets_na_values() -> None:
    records = [_delivery_record(consumer_number="11111111")]
    extraction_records = [_extraction_record(consumer_number="96076255")]

    enriched = DeliveryEnricher(
        EnrichmentConfig(enabled=True)
    ).enrich(records, extraction_records)

    assert len(enriched) == 1
    assert enriched[0].mandatory_inspection_due == "NA"
    assert enriched[0].biometric_due == "NA"
    assert enriched[0].suraksha_tube_due == "NA"
    assert enriched[0].online_payment == "NA"


def test_enrich_duplicate_same_values_does_not_fail() -> None:
    records = [_delivery_record()]
    extraction_records = [
        _extraction_record(),
        _extraction_record(),
    ]

    enriched = DeliveryEnricher(
        EnrichmentConfig(enabled=True)
    ).enrich(records, extraction_records)

    assert len(enriched) == 1
    assert enriched[0].mandatory_inspection_due == "Y"
    assert enriched[0].biometric_due == "N"
    assert enriched[0].suraksha_tube_due == "Y"
    assert enriched[0].online_payment == "Y"


def test_enrich_conflicting_values_raises_error() -> None:
    records = [_delivery_record()]
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

    with pytest.raises(DeliveryEnricherError):
        DeliveryEnricher(
            EnrichmentConfig(enabled=True)
        ).enrich(records, extraction_records)


def test_enrich_consumer_number_normalization_handles_decimal_artifact() -> None:
    records = [_delivery_record(consumer_number="96076255.0")]
    extraction_records = [_extraction_record(consumer_number="96076255")]

    enriched = DeliveryEnricher(
        EnrichmentConfig(enabled=True)
    ).enrich(records, extraction_records)

    assert len(enriched) == 1
    assert enriched[0].mandatory_inspection_due == "Y"
    assert enriched[0].online_payment == "Y"


def test_enrich_disabled_returns_original_records() -> None:
    records = [_delivery_record()]
    extraction_records = [_extraction_record()]

    enriched = DeliveryEnricher(
        EnrichmentConfig(enabled=False)
    ).enrich(records, extraction_records)

    assert enriched == records