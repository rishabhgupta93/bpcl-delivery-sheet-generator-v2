from bpcl_delivery_sheet_generator.audit import AuditWriter
from bpcl_delivery_sheet_generator.config import AuditConfig, OutputConfig
from bpcl_delivery_sheet_generator.models import ExtractionSummary


def test_audit_writer_writes_enrichment_audit_csv(tmp_path):
    writer = AuditWriter(
        output_config=OutputConfig(output_dir=tmp_path),
        audit_config=AuditConfig(enabled=True),
    )

    path = writer.write_enrichment_audit(
        [
            {
                "consumer_number": "96076255",
                "cash_memo_no": "001",
                "invoice_no": "29218",
                "order_no": "22513",
                "mandatory_inspection_due": "Y",
                "biometric_due": "N",
                "suraksha_tube_due": "Y",
                "online_payment": "N",
                "source_pdf": "memo.pdf",
                "source_page": 1,
                "enrichment_status": "MATCHED",
                "remarks": "",
            }
        ]
    )

    assert path is not None
    assert path.exists()
    assert path.name == "cash_memo_enrichment_audit.csv"

    content = path.read_text(encoding="utf-8")
    assert "consumer_number" in content
    assert "96076255" in content
    assert "MATCHED" in content


def test_audit_writer_writes_extraction_summary_csv(tmp_path):
    writer = AuditWriter(
        output_config=OutputConfig(output_dir=tmp_path),
        audit_config=AuditConfig(enabled=True),
    )

    summary = ExtractionSummary(
        total_csv_records=1,
        total_extracted_records=1,
        matched_records=1,
        unmatched_records=0,
        conflicting_records=0,
        mandatory_inspection_due_count=1,
        biometric_due_count=0,
        suraksha_tube_due_count=1,
        online_payment_count=0,
    )

    path = writer.write_extraction_summary(summary)

    assert path is not None
    assert path.exists()
    assert path.name == "cash_memo_extraction_summary.csv"

    content = path.read_text(encoding="utf-8")
    assert "total_csv_records" in content
    assert "matched_records" in content
    assert "1" in content


def test_audit_writer_disabled_returns_none(tmp_path):
    writer = AuditWriter(
        output_config=OutputConfig(output_dir=tmp_path),
        audit_config=AuditConfig(enabled=False),
    )

    enrichment_path = writer.write_enrichment_audit(
        [{"consumer_number": "96076255"}]
    )
    summary_path = writer.write_extraction_summary(
        {"total_csv_records": 1}
    )

    assert enrichment_path is None
    assert summary_path is None
    assert not (tmp_path / "audit").exists()


def test_audit_writer_empty_enrichment_audit_returns_none(tmp_path):
    writer = AuditWriter(
        output_config=OutputConfig(output_dir=tmp_path),
        audit_config=AuditConfig(enabled=True),
    )

    path = writer.write_enrichment_audit([])

    assert path is None
    assert not (
        tmp_path / "audit" / "cash_memo_enrichment_audit.csv"
    ).exists()