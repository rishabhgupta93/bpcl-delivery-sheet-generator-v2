from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from bpcl_delivery_sheet_generator.config import (
    GenerationConfig,
    OutputConfig,
    PdfColumnConfig,
    PdfLayoutConfig,
)
from bpcl_delivery_sheet_generator.models import DeliveryBatch, DeliveryRecord


class PDFRendererError(Exception):
    """Raised when PDF rendering fails."""


@dataclass(frozen=True)
class PDFRenderResult:
    combined_pdf_path: Path | None = None
    split_pdf_paths: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class PDFRenderer:
    output_config: OutputConfig
    generation_config: GenerationConfig
    pdf_config: PdfLayoutConfig
    logger: logging.Logger | None = None

    def render(self, batches: list[DeliveryBatch]) -> PDFRenderResult:
        self._log_info("pdf_render_started")

        self._validate_batches(batches)
        output_dir = self._prepare_output_dir()

        combined_pdf_path: Path | None = None
        split_pdf_paths: list[Path] = []

        if self.generation_config.mode in ("combined", "both"):
            combined_pdf_path = self._render_combined_pdf(
                batches=batches,
                output_dir=output_dir,
            )

        if self.generation_config.mode in ("split", "both"):
            split_pdf_paths = self._render_split_pdfs(
                batches=batches,
                output_dir=output_dir,
            )

        return PDFRenderResult(
            combined_pdf_path=combined_pdf_path,
            split_pdf_paths=split_pdf_paths,
            warnings=[],
        )

    def _validate_batches(self, batches: list[DeliveryBatch]) -> None:
        if not batches:
            raise PDFRendererError(
                "Cannot render PDF because no delivery batches were provided"
            )

        for index, batch in enumerate(batches, start=1):
            if not batch.records:
                raise PDFRendererError(
                    f"Cannot render PDF because delivery batch #{index} has no records"
                )

    def _prepare_output_dir(self) -> Path:
        output_dir = Path(self.output_config.output_dir)

        if self.output_config.create_output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)

        if not output_dir.exists():
            raise PDFRendererError(f"Output directory does not exist: {output_dir}")

        if not output_dir.is_dir():
            raise PDFRendererError(f"Output path is not a directory: {output_dir}")

        return output_dir

    def _render_combined_pdf(
        self,
        *,
        batches: list[DeliveryBatch],
        output_dir: Path,
    ) -> Path:
        output_path = output_dir / self._combined_pdf_filename()

        story = self._build_document_story(
            batches=batches,
            show_operator_sections=True,
        )

        self._write_pdf(
            output_path=output_path,
            story=story,
            delivery_person="ALL DELIVERYMEN",
            total_records=sum(len(batch.records) for batch in batches),
        )

        return output_path

    def _render_split_pdfs(
        self,
        *,
        batches: list[DeliveryBatch],
        output_dir: Path,
    ) -> list[Path]:
        split_dir = output_dir / "split_pdfs"
        split_dir.mkdir(parents=True, exist_ok=True)

        output_paths: list[Path] = []

        for batch in batches:
            operator_name = self._normalize_operator_name(batch.operator_name)
            output_path = split_dir / self._split_pdf_filename(operator_name)

            story = self._build_document_story(
                batches=[batch],
                show_operator_sections=False,
            )

            self._write_pdf(
                output_path=output_path,
                story=story,
                delivery_person=operator_name,
                total_records=len(batch.records),
            )

            output_paths.append(output_path)

        return output_paths

    def _build_document_story(
        self,
        *,
        batches: list[DeliveryBatch],
        show_operator_sections: bool,
    ) -> list[Any]:
        story: list[Any] = [
            Spacer(1, self.pdf_config.story_top_spacer_mm * mm),
        ]

        for batch in batches:
            if show_operator_sections:
                story.extend(self._build_operator_section(batch))
            else:
                story.extend(
                    [
                        self._build_delivery_table(batch),
                        Spacer(1, self.pdf_config.section_bottom_spacer_mm * mm),
                    ]
                )

        return story

    def _build_operator_section(self, batch: DeliveryBatch) -> list[Any]:
        styles = self._styles()
        operator_name = self._normalize_operator_name(batch.operator_name)

        return [
            Paragraph(
                self._escape(
                    f"DELIVERYMAN: {operator_name} | Records: {len(batch.records)}"
                ),
                styles["section_header"],
            ),
            Spacer(1, self.pdf_config.operator_section_spacer_mm * mm),
            self._build_delivery_table(batch),
            Spacer(1, self.pdf_config.section_bottom_spacer_mm * mm),
        ]

    def _build_delivery_table(self, batch: DeliveryBatch) -> LongTable:
        styles = self._styles()

        table_data: list[list[Any]] = [
            [
                Paragraph(
                    self._escape(column.label),
                    styles[
                        "table_header_bold"
                        if column.header_bold
                        else "table_header"
                    ],
                )
                for column in self.pdf_config.columns
            ]
        ]

        for serial_no, record in enumerate(batch.records, start=1):
            row: list[Any] = []

            for column in self.pdf_config.columns:
                value = self._get_cell_value(
                    record=record,
                    column=column,
                    serial_no=serial_no,
                )

                row.append(
                    Paragraph(
                        self._escape(value),
                        styles["cell_bold" if column.value_bold else "cell"],
                    )
                )

            table_data.append(row)

        table = LongTable(
            table_data,
            colWidths=self._column_widths(),
            repeatRows=1,
        )

        table.setStyle(self._table_style())
        return table

    def _get_cell_value(
        self,
        *,
        record: DeliveryRecord,
        column: PdfColumnConfig,
        serial_no: int,
    ) -> str:
        if column.key == "serial_no":
            return str(serial_no)

        if column.key == "address":
            return self._build_full_address(record)

        if column.key in {"otp", "signature"}:
            return column.blank_display_value

        source_field = column.source_field or column.key

        if not hasattr(record, source_field):
            raise PDFRendererError(
                f"Unsupported PDF column source field: {source_field}"
            )

        return self._format_display_value(getattr(record, source_field), column)

    def _format_display_value(
        self,
        value: object,
        column: PdfColumnConfig,
    ) -> str:
        text = "" if value is None else str(value).strip()

        if text == "NA":
            return column.blank_display_value or "-"

        if not text:
            return column.blank_display_value

        return text

    def _build_full_address(self, record: DeliveryRecord) -> str:
        if not self.pdf_config.use_combined_address:
            return str(record.address1 or "").strip()

        parts = [record.address1, record.address2, record.address3]

        return self.pdf_config.address_separator.join(
            str(part).strip()
            for part in parts
            if part and str(part).strip()
        )

    def _column_widths(self) -> list[float]:
        page_width, _ = self._page_size()
        available_width = page_width - (
            (self.pdf_config.left_margin_mm + self.pdf_config.right_margin_mm) * mm
        )

        total_weight = sum(column.width_weight for column in self.pdf_config.columns)

        if total_weight <= 0:
            raise PDFRendererError("Total PDF column width weight must be positive")

        return [
            available_width * column.width_weight / total_weight
            for column in self.pdf_config.columns
        ]

    def _table_style(self) -> TableStyle:
        align_commands = [
            ("ALIGN", (index, 0), (index, -1), column.align.upper())
            for index, column in enumerate(self.pdf_config.columns)
        ]

        writable_box_commands = self._writable_box_style_commands()

        return TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor(self.pdf_config.header_background_hex),
                ),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                (
                    "GRID",
                    (0, 0),
                    (-1, -1),
                    self.pdf_config.base_grid_line_width,
                    colors.HexColor(self.pdf_config.grid_color_hex),
                ),
                (
                    "LINEBELOW",
                    (0, 0),
                    (-1, 0),
                    self.pdf_config.header_line_width,
                    colors.black,
                ),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), self.pdf_config.row_top_padding),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    self.pdf_config.row_bottom_padding,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    self.pdf_config.cell_left_padding,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    self.pdf_config.cell_right_padding,
                ),
                *align_commands,
                *writable_box_commands,
            ]
        )

    def _writable_box_style_commands(self) -> list[tuple]:
        commands: list[tuple] = []

        for index, column in enumerate(self.pdf_config.columns):
            if column.key in {"otp", "signature"}:
                commands.append(
                    (
                        "BOX",
                        (index, 1),
                        (index, -1),
                        self.pdf_config.writable_box_line_width,
                        colors.black,
                    )
                )

        return commands

    def _write_pdf(
        self,
        *,
        output_path: Path,
        story: list[Any],
        delivery_person: str,
        total_records: int,
    ) -> None:
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=self._page_size(),
            leftMargin=self.pdf_config.left_margin_mm * mm,
            rightMargin=self.pdf_config.right_margin_mm * mm,
            topMargin=self.pdf_config.top_margin_mm * mm,
            bottomMargin=self.pdf_config.bottom_margin_mm * mm,
        )

        doc._delivery_person = delivery_person
        doc._total_records = total_records

        doc.build(
            story,
            onFirstPage=self._draw_page_frame,
            onLaterPages=self._draw_page_frame,
        )

    def _draw_page_frame(self, canvas, doc) -> None:
        width, height = self._page_size()
        printed_at = datetime.now().strftime(self.pdf_config.printed_datetime_format)

        delivery_person = getattr(doc, "_delivery_person", "UNKNOWN")
        total_records = getattr(doc, "_total_records", 0)

        left_x = doc.leftMargin
        right_x = width - doc.rightMargin

        header_top_y = height - (self.pdf_config.page_header_y_mm * mm)
        line_gap = self.pdf_config.header_line_gap_mm * mm

        title_y = header_top_y
        meta_y = title_y - line_gap
        price_y = meta_y - line_gap
        divider_y = price_y - (self.pdf_config.divider_gap_mm * mm)

        canvas.saveState()
        canvas.setFillColor(colors.black)

        canvas.setFont("Helvetica-Bold", self.pdf_config.page_header_font_size)
        canvas.drawString(left_x, title_y, self.pdf_config.title)

        canvas.setFont("Helvetica", self.pdf_config.page_meta_font_size)
        canvas.drawRightString(
            right_x,
            title_y,
            f"Page {doc.page} | Printed: {printed_at}",
        )

        if self.pdf_config.show_operator_in_header:
            canvas.drawString(
                left_x,
                meta_y,
                f"Delivery person: {delivery_person} | Total records: {total_records}",
            )

        price_parts: list[str] = []

        if self.pdf_config.price_10kg is not None:
            price_parts.append(
                f"{self.pdf_config.price_10kg_label}: "
                f"{self.pdf_config.currency_symbol}{self.pdf_config.price_10kg:.2f}"
            )

        if self.pdf_config.price_14_2kg is not None:
            price_parts.append(
                f"{self.pdf_config.price_14_2kg_label}: "
                f"{self.pdf_config.currency_symbol}{self.pdf_config.price_14_2kg:.2f}"
            )

        if price_parts:
            canvas.setFont("Helvetica-Bold", self.pdf_config.page_meta_font_size)
            canvas.drawString(left_x, price_y, " | ".join(price_parts))

        canvas.setStrokeColor(colors.HexColor(self.pdf_config.grid_color_hex))
        canvas.setLineWidth(self.pdf_config.divider_line_width)
        canvas.line(left_x, divider_y, right_x, divider_y)

        if self.pdf_config.show_footer_note and self.pdf_config.footer_note.strip():
            canvas.setFillColor(colors.HexColor(self.pdf_config.footer_text_hex))
            canvas.setFont("Helvetica", self.pdf_config.page_footer_font_size)
            canvas.drawString(
                left_x,
                self.pdf_config.footer_y_mm * mm,
                self.pdf_config.footer_note,
            )

        canvas.restoreState()

    def _page_size(self):
        if self.pdf_config.page_size != "A4":
            raise PDFRendererError(
                f"Unsupported PDF page size: {self.pdf_config.page_size}"
            )

        if self.pdf_config.orientation == "landscape":
            return landscape(A4)

        if self.pdf_config.orientation == "portrait":
            return portrait(A4)

        raise PDFRendererError(
            f"Unsupported PDF orientation: {self.pdf_config.orientation}"
        )

    def _styles(self) -> dict[str, ParagraphStyle]:
        sample_styles = getSampleStyleSheet()

        return {
            "section_header": ParagraphStyle(
                "bpcl_section_header",
                parent=sample_styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=self.pdf_config.section_header_font_size,
                leading=self.pdf_config.section_header_leading,
                spaceBefore=2,
                spaceAfter=2,
            ),
            "table_header": ParagraphStyle(
                "bpcl_table_header",
                parent=sample_styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=self.pdf_config.table_header_font_size,
                leading=self.pdf_config.table_header_leading,
            ),
            "table_header_bold": ParagraphStyle(
                "bpcl_table_header_bold",
                parent=sample_styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=self.pdf_config.table_header_font_size,
                leading=self.pdf_config.table_header_leading,
            ),
            "cell": ParagraphStyle(
                "bpcl_cell",
                parent=sample_styles["BodyText"],
                fontName="Helvetica",
                fontSize=self.pdf_config.table_cell_font_size,
                leading=self.pdf_config.table_cell_leading,
            ),
            "cell_bold": ParagraphStyle(
                "bpcl_cell_bold",
                parent=sample_styles["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=self.pdf_config.table_cell_font_size,
                leading=self.pdf_config.table_cell_leading,
            ),
        }

    @staticmethod
    def _normalize_operator_name(value: str) -> str:
        value = (value or "").strip()
        return value or "UNKNOWN"

    @staticmethod
    def _slugify(value: str) -> str:
        value = (value or "").strip().upper()
        value = re.sub(r"[^A-Z0-9]+", "_", value).strip("_")
        return value or "UNKNOWN"

    @staticmethod
    def _combined_pdf_filename() -> str:
        return "delivery_sheet_all_deliverymen.pdf"

    def _split_pdf_filename(self, operator_name: str) -> str:
        return f"delivery_sheet_{self._slugify(operator_name)}.pdf"

    @staticmethod
    def _escape(text: object) -> str:
        return (
            str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _log_info(self, event: str, **metadata: object) -> None:
        if not self.logger:
            return

        if metadata:
            self.logger.info("%s | %s", event, metadata)
        else:
            self.logger.info("%s", event)