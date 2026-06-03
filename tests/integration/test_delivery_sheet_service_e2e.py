from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from bpcl_delivery_sheet_generator.config import PackageConfig
from bpcl_delivery_sheet_generator.services.service import DeliverySheetService


TEST_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def test_delivery_sheet_service_e2e_generates_expected_outputs(tmp_path):
    csv_path = TEST_DATA_DIR / "CashMemoGeneratedList.csv"
    zip_path = TEST_DATA_DIR / "cashmemopdf.zip"

    assert csv_path.exists(), f"Missing test CSV: {csv_path}"
    assert zip_path.exists(), f"Missing test ZIP: {zip_path}"

    config = PackageConfig.default(
        csv_path=csv_path,
        cash_memo_zip_path=zip_path,
        output_dir=tmp_path,
    )

    config = replace(
        config,
        enrichment=replace(
            config.enrichment,
            enabled=True,
        ),
    )

    result = DeliverySheetService(config=config).generate()

    assert result.total_input_rows > 0
    assert result.total_output_rows == result.total_input_rows
    assert result.total_batches > 0

    assert result.combined_pdf_path is not None
    assert result.combined_pdf_path.exists()
    assert result.combined_pdf_path.suffix.lower() == ".pdf"

    assert result.split_pdf_paths
    for pdf_path in result.split_pdf_paths:
        assert pdf_path.exists()
        assert pdf_path.suffix.lower() == ".pdf"

    assert result.enrichment_audit_path is not None
    assert result.enrichment_audit_path.exists()
    assert result.enrichment_audit_path.suffix.lower() == ".csv"

    assert result.extraction_summary_path is not None
    assert result.extraction_summary_path.exists()
    assert result.extraction_summary_path.suffix.lower() == ".csv"

    assert result.zip_path is not None
    assert result.zip_path.exists()
    assert result.zip_path.suffix.lower() == ".zip"