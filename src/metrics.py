"""Метрики качества модели и эксперименты валидации (см. раздел 3.3.3 ВКР).

Содержит:
* базовые точечные метрики WAPE / MAE / RMSE;
* проверку калибровки квантилей;
* чувствительность WAPE к обработке дефицитных дней;
* эксперимент с прогнозной погодой 
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ──────────────────────────────────────────────────────────────────────
# 1. ТОЧЕЧНЫЕ МЕТРИКИ
# ──────────────────────────────────────────────────────────────────────
def wape(y_true: pd.Series, y_pred: pd.Series) -> float:
    """Weighted Absolute Percentage Error — основная метрика ВКР."""
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    denom = np.sum(np.abs(y_true))
    if denom == 0:
        return float("nan")
    return float(np.sum(np.abs(y_true - y_pred)) / denom * 100)


def mae(y_true: pd.Series, y_pred: pd.Series) -> float:
    return float(np.mean(np.abs(np.asarray(y_true) - np.asarray(y_pred))))


def rmse(y_true: pd.Series, y_pred: pd.Series) -> float:
    return float(np.sqrt(np.mean((np.asarray(y_true) - np.asarray(y_pred)) ** 2)))


# ──────────────────────────────────────────────────────────────────────
# 2. КАЛИБРОВКА КВАНТИЛЕЙ (раздел 3.3.3.4 ВКР)
# ──────────────────────────────────────────────────────────────────────
def quantile_coverage(y_true: pd.Series, y_pred_quantile: pd.Series) -> float:

    y_true = np.asarray(y_true)
    y_pred_quantile = np.asarray(y_pred_quantile)
    return float(np.mean(y_true <= y_pred_quantile))


def quantile_calibration_table(
    y_true: pd.Series, preds: dict[str, pd.Series]
) -> pd.DataFrame:

    rows = []
    targets = {"q80": 0.80, "q90": 0.90, "q95": 0.95}
    for name, target in targets.items():
        if name not in preds:
            continue
        cov = quantile_coverage(y_true, preds[name])
        deviation_pp = round((cov - target) * 100, 1)
        rows.append({
            "Квантиль": name,
            "Ожидаемое покрытие, %": round(target * 100, 1),
            "Фактическое покрытие, %": round(cov * 100, 1),
            "Отклонение, п.п.": deviation_pp,
            "Калибровка": "OK" if abs(deviation_pp) <= 5 else "требует пересмотра",
        })
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────
# 3. ЧУВСТВИТЕЛЬНОСТЬ WAPE К ОБРАБОТКЕ ДЕФИЦИТНЫХ ДНЕЙ
# ──────────────────────────────────────────────────────────────────────
def wape_robustness(
    df: pd.DataFrame, y_pred_col: str = "pred_q50"
) -> pd.DataFrame:
    """Три варианта расчёта WAPE: без дефицита / с дефицитом / с интерполяцией.

    Ожидается, что DataFrame содержит колонки:
        demand_qty, is_deficit, rolling_mean_7d, <y_pred_col>
    """
    rows = []

    no_def = df[df["is_deficit"] == 0]
    rows.append({
        "Сценарий": "1. Без дефицитных дней (текущий)",
        "N набл.": len(no_def),
        "WAPE, %": round(wape(no_def["demand_qty"], no_def[y_pred_col]), 2),
    })

    full = df.copy()
    rows.append({
        "Сценарий": "2. С дефицитными днями как фактом iiko",
        "N набл.": len(full),
        "WAPE, %": round(wape(full["demand_qty"], full[y_pred_col]), 2),
    })

    interp = df.copy()
    interp.loc[interp["is_deficit"] == 1, "demand_qty"] = interp.loc[
        interp["is_deficit"] == 1, "rolling_mean_7d"
    ]
    interp = interp.dropna(subset=["demand_qty"])
    rows.append({
        "Сценарий": "3. С интерполированным спросом (rolling_mean_7d)",
        "N набл.": len(interp),
        "WAPE, %": round(wape(interp["demand_qty"], interp[y_pred_col]), 2),
    })

    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────
# 4. ЭКСПЕРИМЕНТ С ПРОГНОЗНОЙ ПОГОДОЙ (раздел 3.3.3.5)
# ──────────────────────────────────────────────────────────────────────
def weather_forecast_experiment(
    model,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    weather_noise_sigma: float = 2.0,
    seed: int = 42,
) -> dict[str, float]:
    """Сравнивает WAPE модели на фактической vs прогнозной погоде.

    Имитация прогнозной погоды: к фактической температуре в тестовом
    периоде добавляется гауссовский шум σ = 2°C (типичная ошибка
    прогноза погоды на горизонте 7 дней).

    Возвращает словарь с двумя значениями WAPE.
    """
    rng = np.random.default_rng(seed)

    pred_actual = model.predict(X_test)
    wape_actual = wape(y_test, pd.Series(pred_actual, index=y_test.index))

    X_noisy = X_test.copy()
    if "temperature_c" in X_noisy.columns:
        X_noisy["temperature_c"] = X_noisy["temperature_c"] + rng.normal(
            0, weather_noise_sigma, size=len(X_noisy)
        )
    pred_noisy = model.predict(X_noisy)
    wape_noisy = wape(y_test, pd.Series(pred_noisy, index=y_test.index))

    return {
        "wape_actual_weather_%": round(wape_actual, 2),
        "wape_forecast_weather_%": round(wape_noisy, 2),
        "delta_pp": round(wape_noisy - wape_actual, 2),
    }
