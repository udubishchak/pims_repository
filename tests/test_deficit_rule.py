"""Контрольные сценарии для алгоритма обнаружения дефицитных дней."""
from __future__ import annotations

import pandas as pd

from src.deficit_detector import detect


def _make_dfs(stock_open: list[float], demand: list[float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range("2025-01-01", periods=len(demand), freq="D")
    sales = pd.DataFrame({
        "location_id": [1] * len(demand),
        "product_id": [1] * len(demand),
        "date": dates,
        "demand_qty": demand,
    })
    stock = sales.copy().drop(columns="demand_qty")
    stock["stock_open"] = stock_open
    return sales, stock


def test_typical_deficit_day_flagged():
    stock = [10] * 7 + [0.5]  # на 8-й день остаток падает
    demand = [10] * 7 + [1.0]  # и расход падает
    sales, st = _make_dfs(stock, demand)
    df = detect(sales, st)
    assert df.iloc[7]["is_deficit"] == 1


def test_low_stock_normal_demand_not_flagged():
    """Низкий остаток, но расход на уровне — это не цензурирование."""
    stock = [10] * 7 + [0.5]
    demand = [10] * 8
    sales, st = _make_dfs(stock, demand)
    df = detect(sales, st)
    assert df.iloc[7]["is_deficit"] == 0


def test_zero_demand_normal_stock_not_flagged():
    """Нулевой расход при полных остатках — выходной/отсутствие спроса."""
    stock = [10] * 8
    demand = [10] * 7 + [0.0]
    sales, st = _make_dfs(stock, demand)
    df = detect(sales, st)
    assert df.iloc[7]["is_deficit"] == 0
