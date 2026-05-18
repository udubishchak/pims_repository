"""DAG-1 «Утренний полный цикл» (07:00 МСК).

Полный конвейер: ETL → конструирование признаков → переобучение четырёх квантильных
моделей LightGBM → расчёт рекомендаций → запись в recommendation_fact.
Длительность ≈25 минут (укладывается в SLA НФТ-3 ≤30 мин).
"""
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.config import DATA_DIR
from src.etl_pipeline import ETLContext, run as run_etl
from src.feature_builder import build_feature_matrix, split_train_test
from src.generate_recommendations import compute_recommendations
from src.train_lightgbm import predict_quantiles, save_models, train_quantile_models

DEFAULT_ARGS = {
    "owner": "pims-analytics",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "start_date": datetime(2026, 1, 1),
}


def _task_etl(**ctx):
    etl_ctx = ETLContext(location_id=1, run_date=ctx["logical_date"], data_dir=Path(DATA_DIR))
    df = run_etl(etl_ctx)
    df.to_parquet("/tmp/sales_clean.parquet")


def _task_features(**ctx):
    sales = pd.read_parquet("/tmp/sales_clean.parquet")
    weather = pd.read_csv(Path(DATA_DIR) / "weather.csv", parse_dates=["date"])
    promo = pd.read_csv(Path(DATA_DIR) / "promo_calendar.csv", parse_dates=["date"])
    products = pd.read_csv(Path(DATA_DIR) / "products.csv")
    df = build_feature_matrix(sales, weather, promo, products)
    df.to_parquet("/tmp/features.parquet")


def _task_train(**ctx):
    df = pd.read_parquet("/tmp/features.parquet")
    train_df, test_df = split_train_test(df)
    models = train_quantile_models(train_df, eval_df=test_df)
    save_models(models, Path("/tmp/models.pkl"))
    preds = predict_quantiles(models, test_df)
    preds.to_parquet("/tmp/predictions.parquet")


def _task_recommend(**ctx):
    preds = pd.read_parquet("/tmp/predictions.parquet")
    products = pd.read_csv(Path(DATA_DIR) / "products.csv")
    stock = pd.read_csv(Path(DATA_DIR) / "stock_fact.csv", parse_dates=["date"])
    recs = compute_recommendations(preds, products, stock)
    recs.to_csv("/tmp/recommendations.csv", index=False)


with DAG(
    "dag1_morning_full_cycle",
    default_args=DEFAULT_ARGS,
    schedule="0 7 * * *",  # 07:00 МСК
    catchup=False,
    description="ETL + переобучение модели + расчёт рекомендаций",
) as dag:
    t_etl = PythonOperator(task_id="load_data", python_callable=_task_etl)
    t_features = PythonOperator(task_id="build_features", python_callable=_task_features)
    t_train = PythonOperator(task_id="train_models", python_callable=_task_train)
    t_recommend = PythonOperator(task_id="generate_recommendations", python_callable=_task_recommend)
    t_etl >> t_features >> t_train >> t_recommend
