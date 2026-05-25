"""Веб-сервис уведомления о дедлайне 20:00 (см. раздел 3.4.4 ВКР).

Архитектура (раздел 3.4.4 ВКР):
* DAG-3 в 19:30 МСК → POST /check_deadline сюда;
* сервис читает order_actual_log на сегодняшнюю дату по каждой точке
  и каналу. Если записи нет — INSERT в deadline_alerts с
  pending_order = TRUE и адресует уведомление в iiko Front;
* плагин iiko Front (внешний модуль) показывает модальное окно
  на кассовом терминале менеджера;
* по нажатию «Заказ отправлен» → POST /order_sent — сбрасывает
  pending_order и пишет запись в order_actual_log.

Полный текст процесса см. в ВКР раздел 3.4.4.
"""
from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("notifier")
app = FastAPI(title="PIMS notifier", version="1.0")


# ──────────────────────────────────────────────────────────────────────
# СХЕМЫ ЗАПРОСОВ / ОТВЕТОВ
# ──────────────────────────────────────────────────────────────────────
class DeadlineCheckRequest(BaseModel):
    location_id: int
    deadline_local: time = time(20, 0)


class DeadlineAlert(BaseModel):
    location_id: int
    channel: int
    pending_order: bool
    message: str
    recommendations_url: str


class OrderSentRequest(BaseModel):
    location_id: int
    channel: int
    manager_id: Optional[int] = None
    actual_qty: Optional[float] = None
    items: Optional[list[dict]] = None  # [{product_id, recommended, actual}]


# ──────────────────────────────────────────────────────────────────────
# ВНУТРЕННИЕ ЗАГЛУШКИ (в проде — SQL к PostgreSQL)
# ──────────────────────────────────────────────────────────────────────
def _has_order_today(location_id: int, channel: int) -> bool:
    """SELECT 1 FROM order_actual_log WHERE date = today() AND ..."""
    return False


def _upsert_deadline_alert(
    location_id: int, channel: int, pending: bool
) -> None:
    """INSERT INTO deadline_alerts (...) ON CONFLICT DO UPDATE SET pending_order = ...

    Таблица deadline_alerts (см. раздел 3.4.4 ВКР):
        (location_id, channel, alert_date, pending_order, created_at)
    """
    logger.info(
        "deadline_alerts: loc=%s ch=%s pending=%s", location_id, channel, pending
    )


def _record_order_sent(req: OrderSentRequest) -> int:
    """INSERT INTO order_actual_log (...) RETURNING order_id."""
    logger.info(
        "order_actual_log: loc=%s ch=%s manager=%s items=%s",
        req.location_id, req.channel, req.manager_id,
        len(req.items) if req.items else 0,
    )
    return 0


# ──────────────────────────────────────────────────────────────────────
# REST-ЭНДПОИНТЫ
# ──────────────────────────────────────────────────────────────────────
@app.post("/check_deadline", response_model=list[DeadlineAlert])
def check_deadline(req: DeadlineCheckRequest) -> list[DeadlineAlert]:
    """Вызывается Airflow DAG-3 в 19:30 МСК."""
    alerts: list[DeadlineAlert] = []
    for channel in (1, 2):
        if _has_order_today(req.location_id, channel):
            _upsert_deadline_alert(req.location_id, channel, pending=False)
            continue
        _upsert_deadline_alert(req.location_id, channel, pending=True)
        alerts.append(
            DeadlineAlert(
                location_id=req.location_id,
                channel=channel,
                pending_order=True,
                message=(
                    "Внимание! Дедлайн 20:00 через 30 минут. "
                    f"Заказ по каналу {channel} не отправлен."
                ),
                recommendations_url=(
                    f"https://datalens.yandex.cloud/pims/recs?loc={req.location_id}"
                ),
            )
        )
    return alerts


@app.post("/order_sent")
def order_sent(req: OrderSentRequest) -> dict:
    """Вызывается плагином iiko Front после нажатия «Заказ отправлен»."""
    order_id = _record_order_sent(req)
    _upsert_deadline_alert(req.location_id, req.channel, pending=False)
    return {
        "status": "ok",
        "order_id": order_id,
        "time": datetime.utcnow().isoformat(),
    }


@app.post("/recalculate")
def recalculate(location_id: int) -> dict:
    """Дёргает Airflow DAG-1 ручным запуском (целевой сценарий — см. ВКР 3.5).

    В прототипе используется заглушка; в эксплуатации — Airflow REST API.
    """
    logger.info("manual recalc requested: loc=%s", location_id)
    return {"status": "queued", "location_id": location_id}
