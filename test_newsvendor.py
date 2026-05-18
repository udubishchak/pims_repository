"""Контрольные сценарии newsvendor-коррекции и округления до MOQ/pack_size."""
from __future__ import annotations

import pandas as pd

from src.generate_recommendations import _round_to_pack, newsvendor_adjust


def test_round_below_moq_lifts_to_moq():
    assert _round_to_pack(0.4, pack_size=0.5, moq=1.0) == 1.0


def test_round_ceiling_to_pack_size():
    assert _round_to_pack(1.7, pack_size=0.5, moq=0.5) == 2.0
    assert _round_to_pack(1.0, pack_size=0.5, moq=0.5) == 1.0


def test_newsvendor_case_excess_stock():
    row = pd.Series({
        "stock_open": 100, "forecast_lt": 50, "safety_stock": 10,
        "days_to_expiry": 5, "shelf_open_days": 3, "forecast_3d": 30,
    })
    q, _ = newsvendor_adjust(row, q_calc=50, lead_time=1)
    assert q == 0.0  # избыточный остаток — заказ не нужен


def test_newsvendor_case_expiring_partition():
    row = pd.Series({
        "stock_open": 20, "forecast_lt": 30, "safety_stock": 5,
        "days_to_expiry": 1, "shelf_open_days": 3, "forecast_3d": 20,
    })
    q, _ = newsvendor_adjust(row, q_calc=20, lead_time=2)
    assert q == 35  # 30 + 5: остаток не вычитается (испортится)


def test_newsvendor_caps_perishable():
    row = pd.Series({
        "stock_open": 0, "forecast_lt": 100, "safety_stock": 0,
        "days_to_expiry": 10, "shelf_open_days": 2, "forecast_3d": 40,
    })
    q, rationale = newsvendor_adjust(row, q_calc=100, lead_time=7)
    assert q == 48  # 40 * 1.2 = 48
    assert "скоропортящихся" in rationale
