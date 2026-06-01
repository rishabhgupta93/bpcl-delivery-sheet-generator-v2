from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from bpcl_delivery_sheet_generator.audit import AuditWriter
from bpcl_delivery_sheet_generator.config import PackageConfig
from bpcl_delivery_sheet_generator.enrichers import DeliveryEnricher
from bpcl_delivery_sheet_generator.extractors import CashMemoPDFExtractor
from bpcl_delivery_sheet_generator.models import GenerationResult
from bpcl_delivery_sheet_generator.packaging import ZIPPackager
from bpcl_delivery_sheet_generator.readers import CashMemoZIPReader, CSVReader
from bpcl_delivery_sheet_generator.renderers import PDFRenderer
from bpcl_delivery_sheet_generator.transformers import DeliveryTransformer


class DeliverySheetServiceError(Exception):
    """Raised when delivery sheet generation fails."""


@dataclass
class DeliverySheetService:
    config: PackageConfig
    logger: logging.Logger | None = None

    def __post_init__(self) -> None:
        self.logger = self.logger or logging.getLogger(__name__)

    def _prepare_output_directories(self) -> None:
        output_dir = Path(self.config.output.output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "split_pdfs").mkdir(parents=True, exist_ok=True)
        (output_dir / "audit").mkdir(parents=True, exist_ok=True)
        (output_dir / "_work" / "cash_memo_pdfs").mkdir(parents=True, exist_ok=True)

    def _read_csv(self):
        self.logger.info("delivery_sheet_csv_stage_started")

        df = CSVReader(
            input_config=self.config.input,
            csv_config=self.config.csv,
            logger=self.logger,
        ).read()

        self.logger.info(
            "delivery_sheet_csv_stage_completed",
            extra={"row_count": len(df)},
        )

        return df

    def _transform_to_records(self, df):
        self.logger.info("delivery_sheet_record_transform_started")

        records = DeliveryTransformer(
            csv_config=self.config.csv,
            generation_config=self.config.generation,
            logger=self.logger,
        ).to_records(df)

        self.logger.info(
            "delivery_sheet_record_transform_completed",
            extra={"record_count": len(records)},
        )

        return records

    def _run_enrichment_if_enabled(self, records):
        if not self.config.enrichment.enabled:
            self.logger.info("delivery_sheet_enrichment_skipped")
            return records, None

        self.logger.info("delivery_sheet_enrichment_started")

        pdf_paths = CashMemoZIPReader(
            input_config=self.config.input,
            output_config=self.config.output,
            enrichment_config=self.config.enrichment,
            logger=self.logger,
        ).read()

        extracted_records = CashMemoPDFExtractor(logger=self.logger).extract(pdf_paths)

        enrichment_result = DeliveryEnricher(
            enrichment_config=self.config.enrichment,
            logger=self.logger,
        ).enrich(records, extracted_records)

        self.logger.info(
            "delivery_sheet_enrichment_completed",
            extra={
                "input_records": len(records),
                "extracted_records": len(extracted_records),
                "enriched_records": len(enrichment_result.records),
                "warnings": len(enrichment_result.warnings),
            },
        )

        return enrichment_result.records, enrichment_result

    def _transform_to_batches(self, records):
        self.logger.info("delivery_sheet_batch_transform_started")

        batches = DeliveryTransformer(
            csv_config=self.config.csv,
            generation_config=self.config.generation,
            logger=self.logger,
        ).to_batches(records)

        self.logger.info(
            "delivery_sheet_batch_transform_completed",
            extra={"batch_count": len(batches)},
        )

        return batches

    def _render_pdfs(self, batches):
        self.logger.info("delivery_sheet_pdf_render_started")

        render_result = PDFRenderer(
            output_config=self.config.output,
            generation_config=self.config.generation,
            pdf_config=self.config.pdf,
            logger=self.logger,
        ).render(batches)

        self.logger.info(
            "delivery_sheet_pdf_render_completed",
            extra={
                "combined_pdf_path": str(render_result.combined_pdf_path)
                if render_result.combined_pdf_path
                else None,
                "split_pdf_count": len(render_result.split_pdf_paths),
                "warnings": len(render_result.warnings),
            },
        )

        return render_result

    def _write_audit_outputs(self, enrichment_result):
        if enrichment_result is None:
            self.logger.info("delivery_sheet_audit_skipped")
            return None, None

        self.logger.info("delivery_sheet_audit_write_started")

        audit_writer = AuditWriter(
            output_config=self.config.output,
            audit_config=self.config.audit,
            logger=self.logger,
        )

        enrichment_audit_path = audit_writer.write_enrichment_audit(
            enrichment_result.audit_rows
        )

        extraction_summary_path = audit_writer.write_extraction_summary(
            enrichment_result.summary
        )

        self.logger.info(
            "delivery_sheet_audit_written",
            extra={
                "enrichment_audit_path": str(enrichment_audit_path)
                if enrichment_audit_path
                else None,
                "extraction_summary_path": str(extraction_summary_path)
                if extraction_summary_path
                else None,
            },
        )

        return enrichment_audit_path, extraction_summary_path

    def _create_zip_package(
        self,
        combined_pdf_path,
        split_pdf_paths,
        enrichment_audit_path,
        extraction_summary_path,
    ):
        self.logger.info("delivery_sheet_zip_create_started")

        zip_path = ZIPPackager(
            output_config=self.config.output,
            logger=self.logger,
        ).create_package(
            combined_pdf_path=combined_pdf_path,
            split_pdf_paths=split_pdf_paths,
            enrichment_audit_path=enrichment_audit_path,
            extraction_summary_path=extraction_summary_path,
        )

        self.logger.info(
            "delivery_sheet_zip_created",
            extra={"zip_path": str(zip_path) if zip_path else None},
        )

        return zip_path

    def _build_generation_result(
        self,
        df,
        records,
        batches,
        render_result,
        zip_path,
        enrichment_audit_path,
        extraction_summary_path,
        enrichment_result,
    ) -> GenerationResult:
        warnings: list[str] = []

        warnings.extend(render_result.warnings)

        if enrichment_result is not None:
            warnings.extend(enrichment_result.warnings)

        return GenerationResult(
            total_input_rows=len(df),
            total_output_rows=len(records),
            total_batches=len(batches),
            combined_pdf_path=render_result.combined_pdf_path,
            split_pdf_paths=render_result.split_pdf_paths,
            zip_path=zip_path,
            warnings=warnings,
            enrichment_audit_path=enrichment_audit_path,
            extraction_summary_path=extraction_summary_path,
        )

    def generate(self) -> GenerationResult:
        try:
            self.logger.info("delivery_sheet_generation_started")

            self.config.validate()
            self._prepare_output_directories()

            df = self._read_csv()
            records = self._transform_to_records(df)
            records, enrichment_result = self._run_enrichment_if_enabled(records)
            batches = self._transform_to_batches(records)
            render_result = self._render_pdfs(batches)

            enrichment_audit_path, extraction_summary_path = self._write_audit_outputs(
                enrichment_result
            )

            zip_path = self._create_zip_package(
                combined_pdf_path=render_result.combined_pdf_path,
                split_pdf_paths=render_result.split_pdf_paths,
                enrichment_audit_path=enrichment_audit_path,
                extraction_summary_path=extraction_summary_path,
            )

            result = self._build_generation_result(
                df=df,
                records=records,
                batches=batches,
                render_result=render_result,
                zip_path=zip_path,
                enrichment_audit_path=enrichment_audit_path,
                extraction_summary_path=extraction_summary_path,
                enrichment_result=enrichment_result,
            )

            self.logger.info(
                "delivery_sheet_generation_completed",
                extra={
                    "total_input_rows": result.total_input_rows,
                    "total_output_rows": result.total_output_rows,
                    "total_batches": result.total_batches,
                    "zip_path": str(result.zip_path) if result.zip_path else None,
                    "warnings": len(result.warnings),
                },
            )

            return result

        except Exception as exc:
            self.logger.exception("delivery_sheet_generation_failed")
            raise DeliverySheetServiceError(str(exc)) from exc