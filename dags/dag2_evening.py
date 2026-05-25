"""DAG-2 «Вечернее обновление прогноза» (18:00 МСК).

Лёгкий цикл без переобучения: загружаем продажи и остатки текущего дня
с открытия до 18:00, пересчитываем признаки и применяем утреннюю модель.
Длительность ≈5 минут.
"""
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.config import DATA_DIR
from src.feature_builder import build_feature_matrix
from src.generate_recommendations import compute_recommendations
from src.train_lightgbm import load_models, predict_quantiles


DEFAULT_ARGS = {
    "owner": "pims-analytics",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
    "start_date": datetime(2026, 1, 1),
}


def _task_refresh_features(**ctx):
    sales = pd.read_csv(Path(DATA_DIR) / "sales_intraday.csv", parse_dates=["date"])
    weather = pd.read_csv(Path(DATA_DIR) / "weather.csv", parse_dates=["date"])
    promo = pd.read_csv(Path(DATA_DIR) / "promo_calendar.csv", parse_dates=["date"])
    products = pd.read_csv(Path(DATA_DIR) / "products.csv")
    df = build_feature_matrix(sales, weather, promo, products)
    df.to_parquet("/tmp/features_pm.parquet")


def _task_predict(**ctx):
    df = pd.read_parquet("/tmp/features_pm.parquet")
    models = load_models(Path("/tmp/models.pkl"))
    preds = predict_quantiles(models, df)
    preds.to_parquet("/tmp/predictions_pm.parquet")


def _task_update_recommendations(**ctx):
    preds = pd.read_parquet("/tmp/predictions_pm.parquet")
    products = pd.read_csv(Path(DATA_DIR) / "products.csv")
    stock = pd.read_csv(Path(DATA_DIR) / "stock_fact.csv", parse_dates=["date"])
    recs = compute_recommendations(preds, products, stock)
    recs.to_csv("/tmp/recommendations_pm.csv", index=False)


with DAG(
    "dag2_evening_refresh",
    default_args=DEFAULT_ARGS,
    schedule="0 18 * * *",  # 18:00 МСК
    catchup=False,
    description="Вечернее обновление прогноза без переобучения",
) as dag:
    t_features = PythonOperator(task_id="recompute_features", python_callable=_task_refresh_features)
    t_predict = PythonOperator(task_id="predict", python_callable=_task_predict)
    t_recs = PythonOperator(task_id="update_recommendations", python_callable=_task_update_recommendations)
    t_features >> t_predict >> t_recs
