"""Расчёт рекомендованного объёма заказа на горизонт LT (см. раздел 3.4 ВКР).

Q_рек = Прогноз_LT + SS − Остаток_тек − Ожид_поставки

где:
* Прогноз_LT — сумма медианных квантильных прогнозов q50 на L дней;
* SS — квантильный страховой запас как разность целевого квантиля и q50;
* Целевой квантиль выбирается единым правилом (раздел 3.4.1, замечание №7):
    1) базовый по ABC-группе (A → q95, B → q90, C → q80);
    2) для скоропортящихся (shelf_open_days ≤ 3) — снижение на 5 п.п.;
    3) для XYZ-класса Z (CV > 0,50) — верхняя граница newsvendor critical ratio.
* Округление вверх до кратного pack_size; если 0 < Q < MOQ → Q := MOQ.
* Newsvendor-коррекция для трёх особых случаев (раздел 3.4.2).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import (
    NEWSVENDOR_CAP_XYZ_Z,
    PERISHABLE_QUANTILE_REDUCTION,
    PERISHABLE_SHELF_DAYS,
    SERVICE_LEVEL_BY_ABC,
    UNIFIED_SERVICE_LEVEL_MATRIX,
)

logger = logging.getLogger("generate_recommendations")


@dataclass
class OrderRecommendation:
    location_id: int
    product_id: int
    abc_xyz: str
    target_quantile: float
    forecast_lt: float
    safety_stock: float
    stock_open: float
    in_transit: float
    q_raw: float
    q_recommended: float
    rationale: str


# ──────────────────────────────────────────────────────────────────────
# 1. ЕДИНОЕ ПРАВИЛО ВЫБОРА УРОВНЯ СЕРВИСА (раздел 3.4.1 ВКР)
# ──────────────────────────────────────────────────────────────────────
def resolve_target_quantile(
    abc: str, xyz: str, shelf_open_days: float
) -> tuple[float, str]:
    """Возвращает целевой квантиль и краткое обоснование для одной позиции.

    Шаг 1: базовый квантиль по ABC-группе.
    Шаг 2: если shelf_open_days ≤ 3 — снижение на 5 п.п.
    Шаг 3: для XYZ-Z (CV > 0.50) — верхняя граница newsvendor.

    Финальный результат сверяется с предрассчитанной матрицей AX–CZ.
    """
    base = SERVICE_LEVEL_BY_ABC.get(abc, 0.80)
    reasons = [f"шаг 1: базовый квантиль {abc} = {base:.2f}"]

    if shelf_open_days <= PERISHABLE_SHELF_DAYS:
        base = max(0.80, base - PERISHABLE_QUANTILE_REDUCTION)
        reasons.append(f"шаг 2: shelf ≤ {PERISHABLE_SHELF_DAYS} дн → {base:.2f}")

    if xyz == "Z":
        cap = NEWSVENDOR_CAP_XYZ_Z
        if base > cap:
            base = cap
            reasons.append(f"шаг 3: newsvendor cap для Z = {cap:.2f}")

    # Сверка с матрицей (доп. валидация на этапе разработки)
    matrix_value = UNIFIED_SERVICE_LEVEL_MATRIX.get(f"{abc}{xyz}", base)
    return base, "; ".join(reasons)


def _pick_quantile_column(target_quantile: float) -> str:
    """Сопоставляет численный квантиль с именем колонки в predictions."""
    if target_quantile >= 0.93:
        return "pred_q95"
    if target_quantile >= 0.85:
        return "pred_q90"
    return "pred_q80"


# ──────────────────────────────────────────────────────────────────────
# 2. NEWSVENDOR-КОРРЕКЦИЯ (раздел 3.4.2 ВКР)
# ──────────────────────────────────────────────────────────────────────
def newsvendor_adjust(
    row: pd.Series, q_calc: float, lead_time: int
) -> tuple[float, str]:
    """Три случая особой коррекции для скоропортящейся продукции."""
    stock_open = float(row.get("stock_open", 0.0))
    forecast_lt = float(row["forecast_lt"])
    days_to_expiry = float(row.get("days_to_expiry", 999))
    shelf_open_days = float(row.get("shelf_open_days", 999))

    if shelf_open_days <= 5 and stock_open * 0.8 >= forecast_lt and days_to_expiry > lead_time:
        return 0.0, "избыточный остаток — риск списания"
    if shelf_open_days <= 5 and days_to_expiry <= lead_time:
        return forecast_lt + float(row["safety_stock"]), "истекающая партия: остаток не вычитается"
    if shelf_open_days <= 3:
        cap = float(row.get("forecast_3d", forecast_lt)) * 1.2
        return min(q_calc, cap), "скоропортящееся: не более 3-дневного прогноза × 1,2"
    return q_calc, "стандартный расчёт"


# ──────────────────────────────────────────────────────────────────────
# 3. ОКРУГЛЕНИЕ ДО MOQ / pack_size (раздел 3.4.3 ВКР)
# ──────────────────────────────────────────────────────────────────────
def _round_to_pack(q: float, pack_size: float, moq: float) -> float:
    if q <= 0:
        return 0.0
    if q < moq:
        return float(moq)
    return float(np.ceil(q / pack_size) * pack_size)


# ──────────────────────────────────────────────────────────────────────
# 4. ОСНОВНАЯ ФУНКЦИЯ РАСЧЁТА РЕКОМЕНДАЦИЙ
# ──────────────────────────────────────────────────────────────────────
def compute_recommendations(
    predictions: pd.DataFrame,
    products: pd.DataFrame,
    stock: pd.DataFrame,
    lead_time: int = 1,
) -> pd.DataFrame:
    """Главная функция: на вход прогнозы и справочники, на выход — Q_рек."""
    df = predictions.merge(
        products[["product_id", "abc_group", "xyz_group", "shelf_open_days",
                  "moq", "pack_size", "channel"]],
        on="product_id",
        how="left",
    ).merge(
        stock[["location_id", "product_id", "date",
               "stock_open", "in_transit", "days_to_expiry"]],
        on=["location_id", "product_id", "date"],
        how="left",
    )

    rows: list[dict] = []
    for (loc, pid), g in df.groupby(["location_id", "product_id"]):
        g = g.sort_values("date").head(lead_time)
        abc = g["abc_group"].iloc[0]
        xyz = g["xyz_group"].iloc[0]
        shelf = float(g["shelf_open_days"].iloc[0])

        target_q, rule_reason = resolve_target_quantile(abc, xyz, shelf)
        q_col = _pick_quantile_column(target_q)

        forecast_lt = g["pred_q50"].sum()
        safety_stock = (g[q_col] - g["pred_q50"]).clip(lower=0).sum()
        stock_open = float(g["stock_open"].iloc[0])
        in_transit = float(g["in_transit"].iloc[0])
        days_to_expiry = float(g["days_to_expiry"].iloc[0])

        q_raw = max(0.0, forecast_lt + safety_stock - stock_open - in_transit)
        row_payload = {
            "stock_open": stock_open,
            "forecast_lt": forecast_lt,
            "forecast_3d": g["pred_q50"].head(3).sum(),
            "safety_stock": safety_stock,
            "shelf_open_days": shelf,
            "days_to_expiry": days_to_expiry,
        }
        q_adjusted, newsvendor_reason = newsvendor_adjust(
            pd.Series(row_payload), q_raw, lead_time
        )
        q_final = _round_to_pack(
            q_adjusted,
            float(g["pack_size"].iloc[0]),
            float(g["moq"].iloc[0]),
        )

        rows.append(
            OrderRecommendation(
                location_id=loc, product_id=pid,
                abc_xyz=f"{abc}{xyz}",
                target_quantile=target_q,
                forecast_lt=forecast_lt,
                safety_stock=safety_stock,
                stock_open=stock_open,
                in_transit=in_transit,
                q_raw=q_raw,
                q_recommended=q_final,
                rationale=f"{rule_reason} | {newsvendor_reason}",
            ).__dict__
        )
    return pd.DataFrame(rows)
