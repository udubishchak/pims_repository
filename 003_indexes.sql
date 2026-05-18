-- Индексы и партиционирование (раздел 3.7.2 ВКР)
-- Партиционирование sales_fact / stock_fact по location_id вводится на этапе 3
-- масштабирования (20+ точек, ~1.5 млн строк/год).

CREATE INDEX IF NOT EXISTS idx_sales_fact_date         ON sales_fact (date);
CREATE INDEX IF NOT EXISTS idx_sales_fact_loc_date     ON sales_fact (location_id, date);
CREATE INDEX IF NOT EXISTS idx_sales_fact_deficit      ON sales_fact (is_deficit) WHERE is_deficit = TRUE;

CREATE INDEX IF NOT EXISTS idx_stock_fact_loc_date     ON stock_fact (location_id, date);
CREATE INDEX IF NOT EXISTS idx_writeoffs_loc_date      ON writeoffs_fact (location_id, date);

CREATE INDEX IF NOT EXISTS idx_forecast_active         ON forecast_fact (location_id, date)
    WHERE forecast_dt = (SELECT max(forecast_dt) FROM forecast_fact);

CREATE INDEX IF NOT EXISTS idx_recommendation_recent   ON recommendation_fact (location_id, date DESC);
CREATE INDEX IF NOT EXISTS idx_order_log_sent_at       ON order_actual_log (sent_at DESC);

CREATE INDEX IF NOT EXISTS idx_model_registry_active   ON model_registry (is_active) WHERE is_active = TRUE;
