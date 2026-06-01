from pathlib import Path

import pytest

from bpcl_delivery_sheet_generator.config import (
    PackageConfig,
    PdfColumnConfig,
)
from bpcl_delivery_sheet_generator.models import DeliveryBatch, DeliveryRecord
from bpcl_delivery_sheet_generator.renderers import (
    PDFRenderer,
    PDFRendererError,
    PDFRenderResult,
)
from dataclasses import replace

def _record() -> DeliveryRecord:
    return DeliveryRecord(
        area="A",
        operator_name="OP1",
        booking_date="2026-05-31",
        cash_memo_date="2026-05-31",
        cash_memo_no="001",
        consumer_number="96076255",
        consumer_name="Test Consumer",
        address1="Address 1",
        address2="Address 2",
        address3="Address 3",
        mobile_number="9999999999",
        mandatory_inspection_due="Y",
        biometric_due="N",
        suraksha_tube_due="Y",
        online_payment="N",
    )


def _renderer(tmp_path: Path) -> PDFRenderer:
    cfg = PackageConfig.default(
        csv_path="input.csv",
        output_dir=tmp_path,
    )

    return PDFRenderer(
        output_config=cfg.output,
        generation_config=cfg.generation,
        pdf_config=cfg.pdf,
    )


def _renderer_with_mode(tmp_path: Path, mode: str) -> PDFRenderer:
    cfg = PackageConfig.default(
        csv_path="input.csv",
        output_dir=tmp_path,
    )

    generation_config = replace(cfg.generation, mode=mode)

    return PDFRenderer(
        output_config=cfg.output,
        generation_config=generation_config,
        pdf_config=cfg.pdf,
    )


def test_pdf_renderer_returns_render_result_for_valid_batches(
    tmp_path: Path,
) -> None:
    renderer = _renderer(tmp_path)

    result = renderer.render(
        [
            DeliveryBatch(
                operator_name="OP1",
                records=[_record()],
            )
        ]
    )

    assert isinstance(result, PDFRenderResult)

    assert result.combined_pdf_path is not None
    assert result.combined_pdf_path.exists()
    assert result.combined_pdf_path.name == "delivery_sheet_all_deliverymen.pdf"

    assert len(result.split_pdf_paths) == 1
    assert result.split_pdf_paths[0].exists()
    assert result.split_pdf_paths[0].name == "delivery_sheet_OP1.pdf"

    assert result.warnings == []


def test_pdf_renderer_creates_output_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "nested" / "out"
    cfg = PackageConfig.default(
        csv_path="input.csv",
        output_dir=output_dir,
    )

    renderer = PDFRenderer(
        output_config=cfg.output,
        generation_config=cfg.generation,
        pdf_config=cfg.pdf,
    )

    renderer.render(
        [
            DeliveryBatch(
                operator_name="OP1",
                records=[_record()],
            )
        ]
    )

    assert output_dir.exists()
    assert output_dir.is_dir()


def test_pdf_renderer_fails_for_empty_batches(tmp_path: Path) -> None:
    renderer = _renderer(tmp_path)

    with pytest.raises(PDFRendererError, match="no delivery batches"):
        renderer.render([])


def test_pdf_renderer_fails_for_batch_without_records(
    tmp_path: Path,
) -> None:
    renderer = _renderer(tmp_path)

    with pytest.raises(PDFRendererError, match="has no records"):
        renderer.render(
            [
                DeliveryBatch(
                    operator_name="OP1",
                    records=[],
                )
            ]
        )


def test_normalize_operator_name_blank() -> None:
    assert PDFRenderer._normalize_operator_name("") == "UNKNOWN"


def test_slugify_operator_name() -> None:
    assert PDFRenderer._slugify("Ramesh Kumar") == "RAMESH_KUMAR"


def test_combined_pdf_filename() -> None:
    assert (
        PDFRenderer._combined_pdf_filename()
        == "delivery_sheet_all_deliverymen.pdf"
    )


def test_split_pdf_filename(tmp_path: Path) -> None:
    renderer = _renderer(tmp_path)

    assert (
        renderer._split_pdf_filename("Ramesh Kumar")
        == "delivery_sheet_RAMESH_KUMAR.pdf"
    )


def test_build_full_address_joins_non_empty_parts(tmp_path: Path) -> None:
    renderer = _renderer(tmp_path)
    record = _record()

    assert (
        renderer._build_full_address(record)
        == "Address 1, Address 2, Address 3"
    )


def test_build_full_address_skips_empty_parts(tmp_path: Path) -> None:
    renderer = _renderer(tmp_path)

    record = DeliveryRecord(
        area="A",
        operator_name="OP1",
        booking_date="2026-05-31",
        cash_memo_date="2026-05-31",
        cash_memo_no="001",
        consumer_number="96076255",
        consumer_name="Test Consumer",
        address1="Address 1",
        address2="",
        address3="Address 3",
        mobile_number="9999999999",
        mandatory_inspection_due="Y",
        biometric_due="N",
        suraksha_tube_due="Y",
        online_payment="N",
    )

    assert renderer._build_full_address(record) == "Address 1, Address 3"

def test_format_display_value_converts_na_to_blank_display_value(
    tmp_path: Path,
) -> None:
    renderer = _renderer(tmp_path)
    column = PdfColumnConfig(
        key="online_payment",
        label="Online",
        width_weight=1.0,
        blank_display_value="-",
    )

    assert renderer._format_display_value("NA", column) == "-"


def test_get_cell_value_returns_serial_number(tmp_path: Path) -> None:
    renderer = _renderer(tmp_path)
    column = PdfColumnConfig(
        key="serial_no",
        label="S.No",
        width_weight=1.0,
    )

    assert (
        renderer._get_cell_value(
            record=_record(),
            column=column,
            serial_no=7,
        )
        == "7"
    )


def test_get_cell_value_raises_for_unsupported_source_field(
    tmp_path: Path,
) -> None:
    renderer = _renderer(tmp_path)
    column = PdfColumnConfig(
        key="bad_column",
        label="Bad",
        width_weight=1.0,
        source_field="does_not_exist",
    )

    with pytest.raises(PDFRendererError, match="Unsupported PDF column source field"):
        renderer._get_cell_value(
            record=_record(),
            column=column,
            serial_no=1,
        )


def test_combined_mode_creates_only_combined_pdf(
    tmp_path: Path,
) -> None:
    renderer = _renderer_with_mode(tmp_path, "combined")

    result = renderer.render(
        [
            DeliveryBatch(
                operator_name="OP1",
                records=[_record()],
            )
        ]
    )

    assert result.combined_pdf_path is not None
    assert result.combined_pdf_path.exists()
    assert result.split_pdf_paths == []


def test_split_mode_creates_only_split_pdfs(
    tmp_path: Path,
) -> None:
    renderer = _renderer_with_mode(tmp_path, "split")

    result = renderer.render(
        [
            DeliveryBatch(
                operator_name="OP1",
                records=[_record()],
            )
        ]
    )

    assert result.combined_pdf_path is None
    assert len(result.split_pdf_paths) == 1
    assert result.split_pdf_paths[0].exists()


def test_both_mode_creates_combined_and_split_pdfs(
    tmp_path: Path,
) -> None:
    renderer = _renderer_with_mode(tmp_path, "both")

    result = renderer.render(
        [
            DeliveryBatch(
                operator_name="OP1",
                records=[_record()],
            )
        ]
    )

    assert result.combined_pdf_path is not None
    assert result.combined_pdf_path.exists()
    assert len(result.split_pdf_paths) == 1
    assert result.split_pdf_paths[0].exists()