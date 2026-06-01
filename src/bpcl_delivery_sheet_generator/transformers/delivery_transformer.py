from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from bpcl_delivery_sheet_generator.config import CsvConfig, GenerationConfig
from bpcl_delivery_sheet_generator.models import DeliveryBatch, DeliveryRecord


class DeliveryTransformerError(Exception):
    """Raised when delivery transformation fails."""


@dataclass
class DeliveryTransformer:
    csv_config: CsvConfig
    generation_config: GenerationConfig
    logger: logging.Logger | None = None

    def to_records(self, df) -> list[DeliveryRecord]:
        if df is None or df.empty:
            raise DeliveryTransformerError("Cannot transform an empty DataFrame.")

        self._log_info("delivery_transform_records_started", row_count=len(df))
        self._validate_column_mapping(df)

        records: list[DeliveryRecord] = []

        for _, row in df.iterrows():
            try:
                records.append(
                    DeliveryRecord(
                        area=self._get_mapped_value(row, "area"),
                        operator_name=self._get_mapped_value(row, "operator_name"),
                        booking_date=self._get_mapped_value(row, "booking_date"),
                        cash_memo_date=self._get_mapped_value(row, "cash_memo_date"),
                        cash_memo_no=self._get_mapped_value(row, "cash_memo_no", strip_decimal_artifact=True),
                        consumer_number=self._get_mapped_value(row, "consumer_number", strip_decimal_artifact=True),
                        consumer_name=self._get_mapped_value(row, "consumer_name"),
                        address1=self._get_mapped_value(row, "address1"),
                        address2=self._get_mapped_value(row, "address2"),
                        address3=self._get_mapped_value(row, "address3"),
                        mobile_number=self._get_mapped_value(row, "mobile_number", strip_decimal_artifact=True),
                    )
                )
            except DeliveryTransformerError:
                raise
            except Exception as exc:
                raise DeliveryTransformerError(
                    f"Failed to create DeliveryRecord: {exc}"
                ) from exc

        self._log_info("delivery_transform_records_created", record_count=len(records))
        return records

    def to_batches(self, records: list[DeliveryRecord]) -> list[DeliveryBatch]:
        if not records:
            return []

        group_by = self.generation_config.group_by
        sort_by = list(self.generation_config.sort_by)

        self._log_info(
            "delivery_transform_batches_started",
            record_count=len(records),
            group_by=group_by,
            sort_by=sort_by,
        )

        self._validate_record_field(group_by)

        for field_name in sort_by:
            self._validate_record_field(field_name)

        sorted_records = sorted(
            records,
            key=lambda record: self._record_sort_key(record, sort_by),
        )

        grouped_records: dict[str, list[DeliveryRecord]] = defaultdict(list)

        for record in sorted_records:
            group_value = self._normalize_group_value(getattr(record, group_by))
            grouped_records[group_value].append(record)

        batches = [
            DeliveryBatch(operator_name=operator_name, records=batch_records)
            for operator_name, batch_records in grouped_records.items()
        ]

        self._log_info("delivery_transform_batches_created", batch_count=len(batches))
        return batches

    def _validate_column_mapping(self, df) -> None:
        missing_columns = [
            source_column
            for source_column in self.csv_config.column_mapping.keys()
            if source_column not in df.columns
        ]

        if missing_columns:
            raise DeliveryTransformerError(
                "Missing mapped source columns: "
                + ", ".join(sorted(missing_columns))
            )

    def _get_mapped_value(
        self,
        row,
        canonical_field: str,
        *,
        strip_decimal_artifact: bool = False,
    ) -> str:
        source_column = self._get_source_column(canonical_field)
        return self._normalize_value(
            row[source_column],
            strip_decimal_artifact=strip_decimal_artifact,
        )

    def _get_source_column(self, canonical_field: str) -> str:
        for source_column, mapped_field in self.csv_config.column_mapping.items():
            if mapped_field == canonical_field:
                return source_column

        raise DeliveryTransformerError(
            f"No source column configured for canonical field: {canonical_field}"
        )

    def _validate_record_field(self, field_name: str) -> None:
        if field_name not in DeliveryRecord.__dataclass_fields__:
            raise DeliveryTransformerError(
                f"Unsupported DeliveryRecord field: {field_name}"
            )

    def _record_sort_key(
        self,
        record: DeliveryRecord,
        sort_by: list[str],
    ) -> tuple:
        return tuple(
            self._sort_value(getattr(record, field_name))
            for field_name in sort_by
        )

    def _sort_value(self, value: object) -> tuple[int, object]:
        text = self._normalize_value(value)

        if text.isdigit():
            return (0, int(text))

        return (1, text.upper())

    def _normalize_group_value(self, value: object) -> str:
        text = self._normalize_value(value)
        return text if text else "UNKNOWN"

    def _normalize_value(
        self,
        value: object,
        *,
        strip_decimal_artifact: bool = False,
    ) -> str:
        if value is None:
            return ""

        text = str(value).strip()

        if text.lower() == "nan":
            return ""

        if strip_decimal_artifact and text.endswith(".0"):
            text = text[:-2]

        return text

    def _log_info(self, event: str, **metadata: object) -> None:
        if self.logger:
            self.logger.info("%s | %s", event, metadata)