-- Минимальный seed: одна пилотная точка, несколько ингредиентов и кластеров.

INSERT INTO dim_locations (location_id, name, city, address, latitude, longitude, location_type, open_date, cluster_id)
VALUES (1, 'ПИМС Москва – Тверская', 'Москва', 'ул. Тверская, д. 1', 55.764500, 37.609000, 'street', '2020-03-15', 1)
ON CONFLICT DO NOTHING;

INSERT INTO dim_products (product_id, name, unit, purchase_price, sale_price, abc_group, xyz_group,
                          shelf_closed_days, shelf_open_days, moq, pack_size, channel) VALUES
(1,  'Молоко топлёное',     'кг', 180, 1667, 'A', 'Y', 7, 3, 1.0, 1.0, 2),
(2,  'Крем сливочный',      'кг', 360, 3000, 'A', 'Z', 5, 2, 0.5, 0.5, 2),
(3,  'Кофе Гейша',          'кг', 1200, 12000, 'A', 'Z', 90, 30, 0.25, 0.25, 1),
(4,  'Клубника свежая',     'кг', 360, 3125, 'A', 'Z', 4, 2, 0.5, 0.5, 2),
(5,  'Молоко кокосовое AROY-D', 'л', 240, 2200, 'A', 'Y', 21, 5, 1.0, 1.0, 1),
(6,  'Личи ягоды',          'кг', 480, 4000, 'B', 'Z', 7, 3, 0.3, 0.3, 2),
(7,  'Пюре манго',          'кг', 320, 2800, 'B', 'Z', 30, 7, 1.0, 1.0, 1),
(8,  'Сироп ванильный',     'л', 280, 2500, 'B', 'Y', 365, 90, 1.0, 1.0, 1),
(9,  'Лайм',                'кг', 220, 1800, 'C', 'Z', 5, 2, 0.5, 0.5, 2),
(10, 'JellyBalls',          'кг', 420, 3500, 'C', 'Y', 60, 14, 1.0, 1.0, 1)
ON CONFLICT DO NOTHING;
