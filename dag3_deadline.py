"""DAG-3 «Уведомление о дедлайне» (19:30 МСК).

Проверяет order_actual_log на наличие заказа за текущую дату для каждого канала.
Если заказ не зафиксирован — отправляет POST в notifier-сервис, который шлёт
модальное уведомление на iiko Front (касса менеджера).
"""
from datetime import datetime, timedelta

import requests
from airflow import DAG
from airflow.operators.python import PythonOperator

DEFAULT_ARGS = {
    "owner": "pims-analytics",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(seconds=30),
    "start_date": datetime(2026, 1, 1),
}

NOTIFIER_URL = "http://notifier:8000/check_deadline"


def _task_check_deadline(**ctx):
    for location_id in (1,):  # на этапе пилота — одна точка
        resp = requests.post(NOTIFIER_URL, json={"location_id": location_id}, timeout=10)
        resp.raise_for_status()
        alerts = resp.json()
        if alerts:
            print(f"⚠ {location_id}: pending order(s): {alerts}")


with DAG(
    "dag3_deadline_alert",
    default_args=DEFAULT_ARGS,
    schedule="30 19 * * *",  # 19:30 МСК
    catchup=False,
    description="Алерт менеджеру при отсутствии записи об отправленном заказе",
) as dag:
    PythonOperator(task_id="check_deadline", python_callable=_task_check_deadline)
