import pandas as pd
import pytest

from bpcl_delivery_sheet_generator.config import PackageConfig
from bpcl_delivery_sheet_generator.models import DeliveryRecord
from bpcl_delivery_sheet_generator.transformers import (
    DeliveryTransformer,
    DeliveryTransformerError,
)


def make_transformer() -> DeliveryTransformer:
    cfg = PackageConfig.default(csv_path="input.csv", output_dir="out")
    return DeliveryTransformer(cfg.csv, cfg.generation)


def make_valid_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "AreaDescription": " A ",
                "eKYCOperatorName": " OP1 ",
                "BookDate": "2026-05-31",
                "CashMemoDate": "2026-05-31",
                "CashMemoNo": "001.0",
                "ConsumerNumber": "96076255.0",
                "ConsumerName": " Test User ",
                "Address1": " A1 ",
                "Address2": " A2 ",
                "Address3": " A3 ",
                "MobileNumber": "9999999999.0",
            }
        ]
    )


def test_to_records_maps_and_normalizes_csv_values():
    transformer = make_transformer()

    records = transformer.to_records(make_valid_dataframe())

    assert len(records) == 1
    assert records[0] == DeliveryRecord(
        area="A",
        operator_name="OP1",
        booking_date="2026-05-31",
        cash_memo_date="2026-05-31",
        cash_memo_no="001",
        consumer_number="96076255",
        consumer_name="Test User",
        address1="A1",
        address2="A2",
        address3="A3",
        mobile_number="9999999999",
    )


def test_to_records_fails_for_empty_dataframe():
    transformer = make_transformer()

    with pytest.raises(DeliveryTransformerError, match="empty DataFrame"):
        transformer.to_records(pd.DataFrame())


def test_to_records_fails_for_missing_mapped_source_column():
    transformer = make_transformer()
    df = make_valid_dataframe().drop(columns=["ConsumerNumber"])

    with pytest.raises(DeliveryTransformerError, match="Missing mapped source columns"):
        transformer.to_records(df)


def test_to_batches_sorts_records_and_groups_by_operator():
    transformer = make_transformer()

    records = [
        DeliveryRecord(
            area="A",
            operator_name="OP2",
            booking_date="2026-05-31",
            cash_memo_date="2026-05-31",
            cash_memo_no="10",
            consumer_number="2",
            consumer_name="B",
            address1="",
            address2="",
            address3="",
            mobile_number="",
        ),
        DeliveryRecord(
            area="A",
            operator_name="OP1",
            booking_date="2026-05-31",
            cash_memo_date="2026-05-31",
            cash_memo_no="2",
            consumer_number="1",
            consumer_name="A",
            address1="",
            address2="",
            address3="",
            mobile_number="",
        ),
    ]

    batches = transformer.to_batches(records)

    assert [batch.operator_name for batch in batches] == ["OP1", "OP2"]
    assert [record.cash_memo_no for record in batches[0].records] == ["2"]
    assert [record.cash_memo_no for record in batches[1].records] == ["10"]


def test_to_batches_uses_unknown_for_blank_operator():
    transformer = make_transformer()

    records = [
        DeliveryRecord(
            area="A",
            operator_name="",
            booking_date="2026-05-31",
            cash_memo_date="2026-05-31",
            cash_memo_no="1",
            consumer_number="1",
            consumer_name="A",
            address1="",
            address2="",
            address3="",
            mobile_number="",
        )
    ]

    batches = transformer.to_batches(records)

    assert len(batches) == 1
    assert batches[0].operator_name == "UNKNOWN"