"""Smoke-тесты на ETL: загрузка сэмплов и базовая валидация."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.config import DATA_DIR


@pytest.mark.skipif(not (Path(DATA_DIR) / "sales_fact.csv").exists(), reason="sample отсутствует")
def test_sales_sample_loads():
    df = pd.read_csv(Path(DATA_DIR) / "sales_fact.csv", parse_dates=["date"])
    assert {"product_id", "date", "demand_qty"}.issubset(df.columns)
    assert df["demand_qty"].ge(0).all() or df["demand_qty"].isna().any()


@pytest.mark.skipif(not (Path(DATA_DIR) / "products.csv").exists(), reason="sample отсутствует")
def test_products_sample_has_abc():
    df = pd.read_csv(Path(DATA_DIR) / "products.csv")
    assert df["abc_group"].isin(["A", "B", "C"]).all()
