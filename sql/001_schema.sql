-- =====================================================================
-- PIMS — схема PostgreSQL (multi-location, готова к масштабированию)
-- Приложение Б к ВКР, НИУ ВШЭ, 2026
--
-- Все таблицы фактов имеют составной первичный ключ, включающий
-- location_id, что обеспечивает корректность UPSERT при работе
-- одновременно с несколькими точками сети (см. раздел 3.7).
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. СПРАВОЧНИКИ (без зависимостей)
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS dim_locations (
    location_id     SERIAL PRIMARY KEY,
    name            TEXT          NOT NULL,
    city            TEXT          NOT NULL,
    address         TEXT,
    latitude        NUMERIC(9, 6) NOT NULL,
    longitude       NUMERIC(9, 6) NOT NULL,
    location_type   TEXT          NOT NULL
                    CHECK (location_type IN ('mall', 'street', 'office', 'transit')),
    open_date       DATE          NOT NULL,
    franchisee_id   INTEGER,
    cluster_id      INTEGER,            -- для холодного старта (раздел 2.1.3)
    is_active       BOOLEAN       NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS dim_products (
    product_id          SERIAL PRIMARY KEY,
    name                TEXT    NOT NULL,
    unit                TEXT    NOT NULL,
    purchase_price      NUMERIC(10, 2),
    sale_price          NUMERIC(10, 2),
    abc_group           CHAR(1) CHECK (abc_group IN ('A', 'B', 'C')),
    xyz_group           CHAR(1) CHECK (xyz_group IN ('X', 'Y', 'Z')),
    shelf_closed_days   INTEGER NOT NULL,
    shelf_open_days     INTEGER NOT NULL,
    moq                 NUMERIC(10, 3) NOT NULL DEFAULT 0,
    pack_size           NUMERIC(10, 3) NOT NULL DEFAULT 1,
    channel             SMALLINT NOT NULL CHECK (channel IN (1, 2))
);

CREATE TABLE IF NOT EXISTS dim_date (
    date           DATE     PRIMARY KEY,
    day_of_week    SMALLINT NOT NULL,
    week_of_year   SMALLINT NOT NULL,
    month          SMALLINT NOT NULL,
    is_weekend     BOOLEAN  NOT NULL,
    is_holiday     BOOLEAN  NOT NULL
);

-- ---------------------------------------------------------------------
-- 2. РЕЕСТР МОДЕЛЕЙ — объявляется ДО forecast_fact, чтобы FK работал
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS model_registry (
    model_id      SERIAL PRIMARY KEY,
    trained_at    TIMESTAMPTZ NOT NULL,
    train_rows    INTEGER     NOT NULL,
    wape_valid    NUMERIC(5, 2),
    storage_uri   TEXT        NOT NULL,
    git_sha       TEXT        NOT NULL,
    is_active     BOOLEAN     NOT NULL DEFAULT FALSE
);

-- ---------------------------------------------------------------------
-- 3. ЗАВИСИМЫЕ СПРАВОЧНИКИ
-- ---------------------------------------------------------------------

-- Погода — отдельный ряд на каждую точку (location_id влияет на координаты)
CREATE TABLE IF NOT EXISTS dim_weather (
    location_id        INTEGER NOT NULL,
    date               DATE    NOT NULL,
    temperature_c      NUMERIC(4, 1),
    humidity_pct       NUMERIC(4, 1),
    precipitation_mm   NUMERIC(5, 2),
    is_actual          BOOLEAN NOT NULL DEFAULT FALSE,    -- факт vs прогноз
    CONSTRAINT pk_dim_weather PRIMARY KEY (location_id, date),
    CONSTRAINT fk_dim_weather_location
        FOREIGN KEY (location_id) REFERENCES dim_locations (location_id)
);

CREATE TABLE IF NOT EXISTS marketing_calendar (
    event_id        SERIAL PRIMARY KEY,
    location_id     INTEGER,                              -- NULL = сетевая акция
    date_from       DATE     NOT NULL,
    date_to         DATE     NOT NULL,
    title           TEXT     NOT NULL,
    is_promo        BOOLEAN  NOT NULL DEFAULT TRUE,
    discount_pct    NUMERIC(4, 1) DEFAULT 0,
    affected_products INTEGER[],
    CONSTRAINT fk_marketing_location
        FOREIGN KEY (location_id) REFERENCES dim_locations (location_id)
);

-- ---------------------------------------------------------------------
-- 4. ФАКТЫ
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS sales_fact (
    location_id   INTEGER  NOT NULL,
    product_id    INTEGER  NOT NULL,
    date          DATE     NOT NULL,
    demand_qty    NUMERIC(12, 3) NOT NULL,
    is_deficit    BOOLEAN  NOT NULL DEFAULT FALSE,
    is_outlier    BOOLEAN  NOT NULL DEFAULT FALSE,
    CONSTRAINT pk_sales_fact PRIMARY KEY (location_id, product_id, date),
    CONSTRAINT fk_sales_location FOREIGN KEY (location_id) REFERENCES dim_locations (location_id),
    CONSTRAINT fk_sales_product  FOREIGN KEY (product_id)  REFERENCES dim_products  (product_id)
);

CREATE TABLE IF NOT EXISTS stock_fact (
    location_id    INTEGER  NOT NULL,
    product_id     INTEGER  NOT NULL,
    date           DATE     NOT NULL,
    stock_open     NUMERIC(12, 3) NOT NULL,
    stock_close    NUMERIC(12, 3) NOT NULL,
    in_transit     NUMERIC(12, 3) NOT NULL DEFAULT 0,
    days_to_expiry SMALLINT,
    CONSTRAINT pk_stock_fact PRIMARY KEY (location_id, product_id, date),
    CONSTRAINT fk_stock_location FOREIGN KEY (location_id) REFERENCES dim_locations (location_id),
    CONSTRAINT fk_stock_product  FOREIGN KEY (product_id)  REFERENCES dim_products  (product_id)
);

CREATE TABLE IF NOT EXISTS writeoffs_fact (
    writeoff_id        BIGSERIAL PRIMARY KEY,
    location_id        INTEGER  NOT NULL,
    product_id         INTEGER  NOT NULL,
    date               DATE     NOT NULL,
    qty                NUMERIC(12, 3) NOT NULL,
    writeoff_cost_rub  NUMERIC(12, 2) NOT NULL,
    reason             TEXT     NOT NULL,
    CONSTRAINT fk_writeoffs_location FOREIGN KEY (location_id) REFERENCES dim_locations (location_id),
    CONSTRAINT fk_writeoffs_product  FOREIGN KEY (product_id)  REFERENCES dim_products  (product_id)
);

CREATE TABLE IF NOT EXISTS forecast_fact (
    location_id INTEGER     NOT NULL,
    product_id  INTEGER     NOT NULL,
    date        DATE        NOT NULL,        -- день, на который сделан прогноз
    forecast_dt TIMESTAMPTZ NOT NULL,        -- когда прогноз был сделан
    pred_q50    NUMERIC(12, 3) NOT NULL,
    pred_q80    NUMERIC(12, 3),
    pred_q90    NUMERIC(12, 3),
    pred_q95    NUMERIC(12, 3),
    model_id    INTEGER,
    CONSTRAINT pk_forecast_fact PRIMARY KEY (location_id, product_id, date, forecast_dt),
    CONSTRAINT fk_forecast_location FOREIGN KEY (location_id) REFERENCES dim_locations  (location_id),
    CONSTRAINT fk_forecast_product  FOREIGN KEY (product_id)  REFERENCES dim_products   (product_id),
    CONSTRAINT fk_forecast_model    FOREIGN KEY (model_id)    REFERENCES model_registry (model_id)
);

CREATE TABLE IF NOT EXISTS recommendation_fact (
    location_id     INTEGER  NOT NULL,
    product_id      INTEGER  NOT NULL,
    date            DATE     NOT NULL,        -- день генерации рекомендации
    channel         SMALLINT NOT NULL,        -- 1 или 2: канал поставки
    forecast_lt     NUMERIC(12, 3) NOT NULL,
    safety_stock    NUMERIC(12, 3) NOT NULL,
    stock_open      NUMERIC(12, 3) NOT NULL,
    q_recommended   NUMERIC(12, 3) NOT NULL,
    rationale       TEXT,
    -- channel ВХОДИТ в PK: одна точка может в один день делать
    -- независимые заказы по двум каналам
    CONSTRAINT pk_recommendation_fact PRIMARY KEY (location_id, product_id, date, channel),
    CONSTRAINT fk_recommendation_location FOREIGN KEY (location_id) REFERENCES dim_locations (location_id),
    CONSTRAINT fk_recommendation_product  FOREIGN KEY (product_id)  REFERENCES dim_products  (product_id)
);

-- ---------------------------------------------------------------------
-- 5. ЖУРНАЛЫ И МЕТРИКИ
-- ---------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS order_actual_log (
    order_id      BIGSERIAL PRIMARY KEY,
    location_id   INTEGER     NOT NULL,
    channel       SMALLINT    NOT NULL,
    sent_at       TIMESTAMPTZ NOT NULL,
    manager_id    INTEGER,
    items         JSONB       NOT NULL,        -- [{product_id, recommended, actual}]
    CONSTRAINT fk_order_log_location FOREIGN KEY (location_id) REFERENCES dim_locations (location_id)
);

CREATE TABLE IF NOT EXISTS model_metrics (
    location_id   INTEGER NOT NULL,
    date          DATE    NOT NULL,
    wape          NUMERIC(5, 2),
    mae           NUMERIC(12, 3),
    rmse          NUMERIC(12, 3),
    q90_coverage  NUMERIC(4, 3),
    CONSTRAINT pk_model_metrics PRIMARY KEY (location_id, date),
    CONSTRAINT fk_model_metrics_location FOREIGN KEY (location_id) REFERENCES dim_locations (location_id)
);

CREATE TABLE IF NOT EXISTS feedback_log (
    feedback_id   BIGSERIAL PRIMARY KEY,
    location_id   INTEGER NOT NULL,
    product_id    INTEGER NOT NULL,
    date          DATE    NOT NULL,
    manager_id    INTEGER,
    delta_qty     NUMERIC(12, 3) NOT NULL,
    comment       TEXT,
    CONSTRAINT fk_feedback_location FOREIGN KEY (location_id) REFERENCES dim_locations (location_id),
    CONSTRAINT fk_feedback_product  FOREIGN KEY (product_id)  REFERENCES dim_products  (product_id)
);

CREATE TABLE IF NOT EXISTS etl_log (
    log_id      BIGSERIAL PRIMARY KEY,
    run_at      TIMESTAMPTZ NOT NULL,
    stage       TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('OK', 'WARNING', 'FAIL')),
    rows_loaded INTEGER,
    message     TEXT
);
