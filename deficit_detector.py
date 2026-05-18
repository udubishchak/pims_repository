"""Обнаружение дефицитных (цензурированных) дней.

Правило (раздел 2.4.4 ВКР):
    stock_ratio = stock_open / rolling_mean_7d  < 0.15
    demand_drop = 1 - daily_qty / rolling_mean_7d  > 0.50

На данных пилотной точки правило срабатывает в 7.3% наблюдений
(1469 из 20100). Совпадение с независимым расчётом доли служит
дополнительной валидацией; ручная проверка 30 случаев — см.
tests/test_deficit_rule.py и Приложение Б.4 ВКР.
"""
from __future__ import annotations

import pandas as pd

from .config import DEFICIT_DEMAND_DROP_THRESHOLD, DEFICIT_STOCK_RATIO_THRESHOLD


def detect(sales: pd.DataFrame, stock: pd.DataFrame) -> pd.DataFrame:
    df = sales.merge(
        stock[["location_id", "product_id", "date", "stock_open"]],
        on=["location_id", "product_id", "date"],
        how="left",
    )
    df = df.sort_values(["location_id", "product_id", "date"]).reset_index(drop=True)
    df["rolling_mean_7d"] = (
        df.groupby(["location_id", "product_id"])["demand_qty"]
        .shift(1)
        .rolling(7, min_periods=3)
        .mean()
        .reset_index(level=[0, 1], drop=True)
    )
    df["stock_ratio"] = df["stock_open"] / df["rolling_mean_7d"]
    df["demand_drop"] = 1 - df["demand_qty"] / df["rolling_mean_7d"]
    df["is_deficit"] = (
        (df["stock_ratio"] < DEFICIT_STOCK_RATIO_THRESHOLD)
        & (df["demand_drop"] > DEFICIT_DEMAND_DROP_THRESHOLD)
    ).astype(int)
    return df


def sample_for_manual_audit(df: pd.DataFrame, n: int = 30, seed: int = 42) -> pd.DataFrame:
    """Выгружает n дефицитных дней для ручной сверки с журналом стоп-листов."""
    flagged = df[df["is_deficit"] == 1]
    return flagged.sample(n=min(n, len(flagged)), random_state=seed).sort_values(
        ["location_id", "product_id", "date"]
    )
