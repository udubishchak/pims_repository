"""Конструирование признаков (23 признака, см. таблицу 3.3 ВКР).

Все лаговые и скользящие признаки вычисляются с явным shift(1) или больше,
чтобы исключить утечку данных из будущего. Тест test_features_no_leakage.py
дополнительно проверяет это: первый элемент после shift должен быть NaN.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .config import FEATURE_COLS, TARGET_COL

logger = logging.getLogger("feature_builder")


def add_lag_features(df: pd.DataFrame, lags=(1, 2, 3, 7, 14, 28)) -> pd.DataFrame:
    df = df.sort_values(["location_id", "product_id", "date"]).reset_index(drop=True)
    g = df.groupby(["location_id", "product_id"])[TARGET_COL]
    for lag in lags:
        df[f"lag_{lag}"] = g.shift(lag)
    return df


def add_rolling_features(df: pd.DataFrame, windows=(7, 14)) -> pd.DataFrame:
    df = df.sort_values(["location_id", "product_id", "date"]).reset_index(drop=True)
    for w in windows:
        rolling = (
            df.groupby(["location_id", "product_id"])[TARGET_COL]
            .shift(1)
            .rolling(w, min_periods=1)
        )
        df[f"roll_mean_{w}"] = rolling.mean().reset_index(level=[0, 1], drop=True)
        df[f"roll_std_{w}"] = rolling.std().reset_index(level=[0, 1], drop=True)
    return df


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["day_of_week"] = df["date"].dt.dayofweek
    df["month"] = df["date"].dt.month
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["is_friday"] = (df["day_of_week"] == 4).astype(int)
    df["is_saturday"] = (df["day_of_week"] == 5).astype(int)
    return df


def add_weather_features(df: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    df = df.merge(weather, on=["date"], how="left")
    df["is_rainy"] = (df["precipitation_mm"].fillna(0) > 1).astype(int)
    return df


def add_promo_features(df: pd.DataFrame, promo: pd.DataFrame) -> pd.DataFrame:
    df = df.merge(promo, on="date", how="left")
    df["is_holiday"] = df.get("is_holiday", 0).fillna(0).astype(int)
    df["is_promo"] = df.get("is_promo", 0).fillna(0).astype(int)
    df["discount_pct"] = df.get("discount_pct", 0).fillna(0)
    return df


def build_feature_matrix(
    sales: pd.DataFrame,
    weather: pd.DataFrame,
    promo: pd.DataFrame,
    products: pd.DataFrame,
) -> pd.DataFrame:
    df = sales.merge(
        products[["product_id", "abc_group", "xyz_group", "shelf_open_days"]],
        on="product_id",
        how="left",
    )
    df = add_weather_features(df, weather)
    df = add_promo_features(df, promo)
    df = add_lag_features(df)
    df = add_rolling_features(df)
    df = add_calendar_features(df)

    # Цензурированные дни и NaN от лагов исключаются из обучения
    train_mask = (df.get("is_deficit", 0) == 0) & df[FEATURE_COLS].notna().all(axis=1)
    logger.info("Чистых строк: %s из %s", f"{train_mask.sum():,}", f"{len(df):,}")

    df["use_for_training"] = train_mask.astype(int)
    return df


def split_train_test(
    df: pd.DataFrame, split_date: str = "2025-10-01"
) -> tuple[pd.DataFrame, pd.DataFrame]:
    split = pd.Timestamp(split_date)
    train = df[(df["date"] < split) & (df["use_for_training"] == 1)].copy()
    test = df[(df["date"] >= split) & (df["use_for_training"] == 1)].copy()
    return train, test
