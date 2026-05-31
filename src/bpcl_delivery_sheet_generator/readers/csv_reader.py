from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from bpcl_delivery_sheet_generator.config import CsvConfig, InputConfig


class CSVReaderError(Exception):
    """Raised when CSV reading or CSV validation fails."""


@dataclass
class CSVReader:
    input_config: InputConfig
    csv_config: CsvConfig
    logger: logging.Logger | None = None

    def read(self) -> pd.DataFrame:
        csv_path = self._validate_csv_path()
        df = self._read_csv(csv_path)
        df = self._clean_column_headers(df)
        self._validate_required_columns(df)
        self._validate_not_empty(df)
        return df

    def _validate_csv_path(self) -> Path:
        csv_path = Path(self.input_config.csv_path)

        if not csv_path.exists():
            raise CSVReaderError(f"CSV file not found: {csv_path}")

        if not csv_path.is_file():
            raise CSVReaderError(f"CSV path is not a file: {csv_path}")

        if csv_path.suffix.lower() != ".csv":
            raise CSVReaderError(f"Input file must be a CSV file: {csv_path}")

        return csv_path

    def _read_csv(self, csv_path: Path) -> pd.DataFrame:
        try:
            return pd.read_csv(
                csv_path,
                skiprows=self.csv_config.skip_rows,
                encoding=self.csv_config.encoding,
                dtype=str,
            )
        except Exception as exc:
            raise CSVReaderError(f"Failed to read CSV file: {csv_path}") from exc

    def _clean_column_headers(self, df: pd.DataFrame) -> pd.DataFrame:
        df.columns = [
            str(column).replace("\ufeff", "").strip()
            for column in df.columns
        ]
        return df

    def _validate_required_columns(self, df: pd.DataFrame) -> None:
        available_columns = set(df.columns)

        missing_columns = [
            column
            for column in self.csv_config.required_columns
            if column not in available_columns
        ]

        if missing_columns:
            missing = ", ".join(missing_columns)
            raise CSVReaderError(f"Missing required CSV columns: {missing}")

    def _validate_not_empty(self, df: pd.DataFrame) -> None:
        if df.empty:
            raise CSVReaderError("CSV contains no delivery records.")