from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
import pandas as pd

from bpcl_delivery_sheet_generator.models import GenerationResult
from bpcl_delivery_sheet_generator.services.service import DeliverySheetService


SERVICE_MODULE = "bpcl_delivery_sheet_generator.services.service"


def test_generate_success_with_enrichment_enabled(tmp_path):
    df = pd.DataFrame({"col": ["row1", "row2"]})

    raw_records = [Mock(name="raw_record_1"), Mock(name="raw_record_2")]
    enriched_records = [Mock(name="enriched_record_1"), Mock(name="enriched_record_2")]
    extracted_records = [Mock(name="extracted_record_1")]
    batches = [Mock(name="batch_1")]

    render_result = SimpleNamespace(
        combined_pdf_path=tmp_path / "delivery_sheet_all_deliverymen.pdf",
        split_pdf_paths=[tmp_path / "split_pdfs" / "delivery_sheet_OP1.pdf"],
        warnings=["render warning"],
    )

    enrichment_result = SimpleNamespace(
        records=enriched_records,
        audit_rows=[{"consumer_number": "96076255"}],
        summary=Mock(name="summary"),
        warnings=["enrichment warning"],
    )

    config = Mock()
    config.input = Mock()
    config.output = Mock(output_dir=tmp_path)
    config.csv = Mock()
    config.generation = Mock()
    config.enrichment = Mock(enabled=True)
    config.pdf = Mock()
    config.audit = Mock()

    enrichment_audit_path = tmp_path / "audit" / "cash_memo_enrichment_audit.csv"
    extraction_summary_path = tmp_path / "audit" / "cash_memo_extraction_summary.csv"
    zip_path = tmp_path / "bpcl_delivery_sheet_package.zip"

    with (
        patch(f"{SERVICE_MODULE}.CSVReader") as csv_reader_cls,
        patch(f"{SERVICE_MODULE}.DeliveryTransformer") as transformer_cls,
        patch(f"{SERVICE_MODULE}.CashMemoZIPReader") as zip_reader_cls,
        patch(f"{SERVICE_MODULE}.CashMemoPDFExtractor") as pdf_extractor_cls,
        patch(f"{SERVICE_MODULE}.DeliveryEnricher") as enricher_cls,
        patch(f"{SERVICE_MODULE}.PDFRenderer") as renderer_cls,
        patch(f"{SERVICE_MODULE}.AuditWriter") as audit_writer_cls,
        patch(f"{SERVICE_MODULE}.ZIPPackager") as zip_packager_cls,
    ):
        csv_reader_cls.return_value.read.return_value = df

        transformer = transformer_cls.return_value
        transformer.to_records.return_value = raw_records
        transformer.to_batches.return_value = batches

        zip_reader_cls.return_value.read.return_value = [tmp_path / "memo.pdf"]
        pdf_extractor_cls.return_value.extract.return_value = extracted_records
        enricher_cls.return_value.enrich.return_value = enrichment_result

        renderer_cls.return_value.render.return_value = render_result

        audit_writer = audit_writer_cls.return_value
        audit_writer.write_enrichment_audit.return_value = enrichment_audit_path
        audit_writer.write_extraction_summary.return_value = extraction_summary_path

        zip_packager_cls.return_value.create_package.return_value = zip_path

        result = DeliverySheetService(config=config).generate()

    assert isinstance(result, GenerationResult)

    config.validate.assert_called_once()

    csv_reader_cls.return_value.read.assert_called_once()
    transformer.to_records.assert_called_once_with(df)

    zip_reader_cls.return_value.read.assert_called_once()
    pdf_extractor_cls.return_value.extract.assert_called_once_with([tmp_path / "memo.pdf"])
    enricher_cls.return_value.enrich.assert_called_once_with(raw_records, extracted_records)

    transformer.to_batches.assert_called_once_with(enriched_records)
    renderer_cls.return_value.render.assert_called_once_with(batches)

    audit_writer.write_enrichment_audit.assert_called_once_with(enrichment_result.audit_rows)
    audit_writer.write_extraction_summary.assert_called_once_with(enrichment_result.summary)

    zip_packager_cls.return_value.create_package.assert_called_once_with(
        combined_pdf_path=render_result.combined_pdf_path,
        split_pdf_paths=render_result.split_pdf_paths,
        enrichment_audit_path=enrichment_audit_path,
        extraction_summary_path=extraction_summary_path,
    )

    assert result.total_input_rows == 2
    assert result.total_output_rows == 2
    assert result.total_batches == 1
    assert result.combined_pdf_path == render_result.combined_pdf_path
    assert result.split_pdf_paths == render_result.split_pdf_paths
    assert result.zip_path == zip_path
    assert result.enrichment_audit_path == enrichment_audit_path
    assert result.extraction_summary_path == extraction_summary_path
    assert result.warnings == ["render warning", "enrichment warning"]

def test_generate_skips_enrichment_when_disabled(tmp_path):
    df = pd.DataFrame({"col": ["row1", "row2"]})

    raw_records = [Mock(name="raw_record_1"), Mock(name="raw_record_2")]
    batches = [Mock(name="batch_1")]

    render_result = SimpleNamespace(
        combined_pdf_path=tmp_path / "delivery_sheet_all_deliverymen.pdf",
        split_pdf_paths=[],
        warnings=[],
    )

    config = Mock()
    config.input = Mock()
    config.output = Mock(output_dir=tmp_path)
    config.csv = Mock()
    config.generation = Mock()
    config.enrichment = Mock(enabled=False)
    config.pdf = Mock()
    config.audit = Mock()

    zip_path = tmp_path / "bpcl_delivery_sheet_package.zip"

    with (
        patch(f"{SERVICE_MODULE}.CSVReader") as csv_reader_cls,
        patch(f"{SERVICE_MODULE}.DeliveryTransformer") as transformer_cls,
        patch(f"{SERVICE_MODULE}.CashMemoZIPReader") as zip_reader_cls,
        patch(f"{SERVICE_MODULE}.CashMemoPDFExtractor") as pdf_extractor_cls,
        patch(f"{SERVICE_MODULE}.DeliveryEnricher") as enricher_cls,
        patch(f"{SERVICE_MODULE}.PDFRenderer") as renderer_cls,
        patch(f"{SERVICE_MODULE}.AuditWriter") as audit_writer_cls,
        patch(f"{SERVICE_MODULE}.ZIPPackager") as zip_packager_cls,
    ):
        csv_reader_cls.return_value.read.return_value = df

        transformer = transformer_cls.return_value
        transformer.to_records.return_value = raw_records
        transformer.to_batches.return_value = batches

        renderer_cls.return_value.render.return_value = render_result
        zip_packager_cls.return_value.create_package.return_value = zip_path

        result = DeliverySheetService(config=config).generate()

    zip_reader_cls.assert_not_called()
    pdf_extractor_cls.assert_not_called()
    enricher_cls.assert_not_called()
    audit_writer_cls.assert_not_called()

    transformer.to_batches.assert_called_once_with(raw_records)

    zip_packager_cls.return_value.create_package.assert_called_once_with(
        combined_pdf_path=render_result.combined_pdf_path,
        split_pdf_paths=render_result.split_pdf_paths,
        enrichment_audit_path=None,
        extraction_summary_path=None,
    )

    assert result.total_input_rows == 2
    assert result.total_output_rows == 2
    assert result.total_batches == 1
    assert result.enrichment_audit_path is None
    assert result.extraction_summary_path is None
    assert result.warnings == []

def test_generate_handles_audit_disabled_via_audit_writer_contract(tmp_path):
    df = pd.DataFrame({"col": ["row1"]})

    raw_records = [Mock(name="raw_record")]
    enriched_records = [Mock(name="enriched_record")]
    extracted_records = [Mock(name="extracted_record")]
    batches = [Mock(name="batch")]

    render_result = SimpleNamespace(
        combined_pdf_path=tmp_path / "delivery_sheet_all_deliverymen.pdf",
        split_pdf_paths=[],
        warnings=[],
    )

    enrichment_result = SimpleNamespace(
        records=enriched_records,
        audit_rows=[{"consumer_number": "96076255"}],
        summary=Mock(name="summary"),
        warnings=[],
    )

    config = Mock()
    config.input = Mock()
    config.output = Mock(output_dir=tmp_path)
    config.csv = Mock()
    config.generation = Mock()
    config.enrichment = Mock(enabled=True)
    config.pdf = Mock()
    config.audit = Mock(enabled=False)

    zip_path = tmp_path / "bpcl_delivery_sheet_package.zip"

    with (
        patch(f"{SERVICE_MODULE}.CSVReader") as csv_reader_cls,
        patch(f"{SERVICE_MODULE}.DeliveryTransformer") as transformer_cls,
        patch(f"{SERVICE_MODULE}.CashMemoZIPReader") as zip_reader_cls,
        patch(f"{SERVICE_MODULE}.CashMemoPDFExtractor") as pdf_extractor_cls,
        patch(f"{SERVICE_MODULE}.DeliveryEnricher") as enricher_cls,
        patch(f"{SERVICE_MODULE}.PDFRenderer") as renderer_cls,
        patch(f"{SERVICE_MODULE}.AuditWriter") as audit_writer_cls,
        patch(f"{SERVICE_MODULE}.ZIPPackager") as zip_packager_cls,
    ):
        csv_reader_cls.return_value.read.return_value = df

        transformer = transformer_cls.return_value
        transformer.to_records.return_value = raw_records
        transformer.to_batches.return_value = batches

        zip_reader_cls.return_value.read.return_value = [tmp_path / "memo.pdf"]
        pdf_extractor_cls.return_value.extract.return_value = extracted_records
        enricher_cls.return_value.enrich.return_value = enrichment_result

        renderer_cls.return_value.render.return_value = render_result

        audit_writer = audit_writer_cls.return_value
        audit_writer.write_enrichment_audit.return_value = None
        audit_writer.write_extraction_summary.return_value = None

        zip_packager_cls.return_value.create_package.return_value = zip_path

        result = DeliverySheetService(config=config).generate()

    audit_writer_cls.assert_called_once()
    audit_writer.write_enrichment_audit.assert_called_once_with(enrichment_result.audit_rows)
    audit_writer.write_extraction_summary.assert_called_once_with(enrichment_result.summary)

    zip_packager_cls.return_value.create_package.assert_called_once_with(
        combined_pdf_path=render_result.combined_pdf_path,
        split_pdf_paths=render_result.split_pdf_paths,
        enrichment_audit_path=None,
        extraction_summary_path=None,
    )

    assert result.enrichment_audit_path is None
    assert result.extraction_summary_path is None

def test_generate_wraps_component_failure(tmp_path):
    config = Mock()
    config.input = Mock()
    config.output = Mock(output_dir=tmp_path)
    config.csv = Mock()
    config.generation = Mock()
    config.enrichment = Mock(enabled=True)
    config.pdf = Mock()
    config.audit = Mock()

    with patch(f"{SERVICE_MODULE}.CSVReader") as csv_reader_cls:
        csv_reader_cls.return_value.read.side_effect = RuntimeError("csv exploded")

        with pytest.raises(Exception) as exc_info:
            DeliverySheetService(config=config).generate()

    assert exc_info.value.__class__.__name__ == "DeliverySheetServiceError"
    assert "csv exploded" in str(exc_info.value)