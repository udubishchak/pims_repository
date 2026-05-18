"""Обучение четырёх квантильных моделей LightGBM (alpha = 0.5/0.8/0.9/0.95).

Используется единая глобальная модель (см. раздел 3.3.2 ВКР):
все ингредиенты × все точки обучаются совместно, паттерны переносятся
между рядами через лаговые признаки.
"""
from __future__ import annotations

import logging
import pickle
from pathlib import Path

import lightgbm as lgb
import pandas as pd

from .config import FEATURE_COLS, LGBM_PARAMS, QUANTILES, TARGET_COL

logger = logging.getLogger("train_lightgbm")


def train_quantile_models(
    train_df: pd.DataFrame, eval_df: pd.DataFrame | None = None
) -> dict[str, lgb.LGBMRegressor]:
    X_train, y_train = train_df[FEATURE_COLS], train_df[TARGET_COL]
    eval_set = None
    if eval_df is not None:
        eval_set = [(eval_df[FEATURE_COLS], eval_df[TARGET_COL])]

    models: dict[str, lgb.LGBMRegressor] = {}
    for name, alpha in QUANTILES.items():
        params = {**LGBM_PARAMS, "objective": "quantile", "alpha": alpha}
        model = lgb.LGBMRegressor(**params)
        model.fit(
            X_train,
            y_train,
            eval_set=eval_set,
            callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)],
        )
        models[name] = model
        logger.info(
            "Модель %s (alpha=%.2f) обучена, best_iter=%s",
            name, alpha, model.best_iteration_,
        )
    return models


def predict_quantiles(
    models: dict[str, lgb.LGBMRegressor], df: pd.DataFrame
) -> pd.DataFrame:
    result = df.copy()
    X = df[FEATURE_COLS]
    for name, model in models.items():
        result[f"pred_{name}"] = model.predict(X)
    return result


def save_models(models: dict[str, lgb.LGBMRegressor], out_path: Path) -> None:
    """Сериализует модели + метаданные. Файл загружается в Object Storage,
    запись метаданных делается отдельной командой в model_registry."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as f:
        pickle.dump(models, f)
    logger.info("Модели сохранены в %s", out_path)


def load_models(path: Path) -> dict[str, lgb.LGBMRegressor]:
    with open(path, "rb") as f:
        return pickle.load(f)
