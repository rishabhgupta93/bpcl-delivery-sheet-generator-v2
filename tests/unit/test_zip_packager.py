import zipfile

import pytest

from bpcl_delivery_sheet_generator.config import OutputConfig
from bpcl_delivery_sheet_generator.packaging import ZIPPackager, ZIPPackagerError


def test_zip_packager_creates_package_with_expected_files(tmp_path):
    combined_pdf = tmp_path / "delivery_sheet_all_deliverymen.pdf"
    combined_pdf.write_bytes(b"combined")

    split_dir = tmp_path / "split_pdfs"
    split_dir.mkdir()
    split_pdf = split_dir / "delivery_sheet_OPERATOR_A.pdf"
    split_pdf.write_bytes(b"split")

    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    enrichment_audit = audit_dir / "cash_memo_enrichment_audit.csv"
    extraction_summary = audit_dir / "cash_memo_extraction_summary.csv"

    enrichment_audit.write_text("consumer_number,status\n96076255,MATCHED\n", encoding="utf-8")
    extraction_summary.write_text("total_csv_records,matched_records\n1,1\n", encoding="utf-8")

    packager = ZIPPackager(output_config=OutputConfig(output_dir=tmp_path))

    package_path = packager.create_package(
        combined_pdf_path=combined_pdf,
        split_pdf_paths=[split_pdf],
        enrichment_audit_path=enrichment_audit,
        extraction_summary_path=extraction_summary,
    )

    assert package_path == tmp_path / "bpcl_delivery_sheet_package.zip"
    assert package_path.exists()

    with zipfile.ZipFile(package_path) as zip_file:
        assert sorted(zip_file.namelist()) == sorted(
            [
                "delivery_sheet_all_deliverymen.pdf",
                "split_pdfs/delivery_sheet_OPERATOR_A.pdf",
                "audit/cash_memo_enrichment_audit.csv",
                "audit/cash_memo_extraction_summary.csv",
            ]
        )


def test_zip_packager_excludes_work_and_input_files_even_if_present(tmp_path):
    (tmp_path / "_work" / "cash_memo_pdfs").mkdir(parents=True)
    (tmp_path / "_work" / "cash_memo_pdfs" / "raw.pdf").write_bytes(b"raw")

    raw_csv = tmp_path / "CashMemoGeneratedList.csv"
    raw_csv.write_text("raw", encoding="utf-8")

    uploaded_zip = tmp_path / "uploaded_cash_memos.zip"
    uploaded_zip.write_bytes(b"zip")

    combined_pdf = tmp_path / "delivery_sheet_all_deliverymen.pdf"
    combined_pdf.write_bytes(b"combined")

    packager = ZIPPackager(output_config=OutputConfig(output_dir=tmp_path))

    package_path = packager.create_package(
        combined_pdf_path=combined_pdf,
        split_pdf_paths=[],
        enrichment_audit_path=None,
        extraction_summary_path=None,
    )

    with zipfile.ZipFile(package_path) as zip_file:
        names = zip_file.namelist()

    assert names == ["delivery_sheet_all_deliverymen.pdf"]
    assert "_work/cash_memo_pdfs/raw.pdf" not in names
    assert "CashMemoGeneratedList.csv" not in names
    assert "uploaded_cash_memos.zip" not in names


def test_zip_packager_returns_none_when_no_files_are_provided(tmp_path):
    packager = ZIPPackager(output_config=OutputConfig(output_dir=tmp_path))

    package_path = packager.create_package(
        combined_pdf_path=None,
        split_pdf_paths=[],
        enrichment_audit_path=None,
        extraction_summary_path=None,
    )

    assert package_path is None
    assert not (tmp_path / "bpcl_delivery_sheet_package.zip").exists()


def test_zip_packager_fails_when_provided_file_is_missing(tmp_path):
    packager = ZIPPackager(output_config=OutputConfig(output_dir=tmp_path))

    with pytest.raises(ZIPPackagerError, match="combined PDF does not exist"):
        packager.create_package(
            combined_pdf_path=tmp_path / "missing.pdf",
            split_pdf_paths=[],
            enrichment_audit_path=None,
            extraction_summary_path=None,
        )