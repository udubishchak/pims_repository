"""Защита от утечки данных из будущего (см. требование к признакам в разделе 3.3.1)."""
from __future__ import annotations

import pandas as pd
import pytest

from src.feature_builder import add_lag_features, add_rolling_features


@pytest.fixture
def synthetic_sales() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=30, freq="D")
    return pd.DataFrame(
        {
            "location_id": [1] * 30,
            "product_id": [1] * 30,
            "date": dates,
            "demand_qty": range(30),
        }
    )


def test_lag_features_first_rows_nan(synthetic_sales):
    df = add_lag_features(synthetic_sales)
    assert pd.isna(df.iloc[0]["lag_1"])
    assert pd.isna(df.iloc[6]["lag_7"])
    assert df.iloc[7]["lag_7"] == 0  # шифт ровно на 7 — первый ненулевой


def test_rolling_uses_shift(synthetic_sales):
    df = add_rolling_features(synthetic_sales)
    # rolling должен использовать значения ДО текущего дня (shift(1)),
    # поэтому roll_mean_7 на день 7 не равен demand_qty день 0..6 включая текущий
    assert df.iloc[7]["roll_mean_7"] == pytest.approx(sum(range(7)) / 7)
