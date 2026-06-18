-- ============================================================
-- Smart Logistics — тестовая база для Postman/DBeaver практики
-- ============================================================

CREATE TABLE cities (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    region VARCHAR(100)
);

INSERT INTO cities (name, region) VALUES
('Москва', 'Московская область'),
('Санкт-Петербург', 'Ленинградская область'),
('Екатеринбург', 'Свердловская область'),
('Новосибирск', 'Новосибирская область'),
('Краснодар', 'Краснодарский край'),
('Казань', 'Республика Татарстан'),
('Пермь', 'Пермский край');

CREATE TABLE vehicle_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL
);

INSERT INTO vehicle_categories (name) VALUES
('Тент'), ('Рефрижератор'), ('Изотерм'), ('Борт открытый'), ('Контейнеровоз'), ('Негабарит');

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    inn VARCHAR(12),
    city_id INT REFERENCES cities(id)
);

INSERT INTO customers (name, inn, city_id) VALUES
('ООО "ТрансГрупп"',         '7701234567',   1),
('ООО "СтройМатериалы"',     '7802345678',   2),
('ИП Сидоров А.В.',          '660345678901', 3),
('ООО "АгроПром"',           '5403456789',   4),
('ООО "ФудЛогистика"',       '2309567890',   5);

CREATE TABLE carriers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    vehicle_plate VARCHAR(20),
    is_accredited BOOLEAN DEFAULT true,
    is_blacklisted BOOLEAN DEFAULT false,
    rating NUMERIC(3,2)
);

INSERT INTO carriers (name, vehicle_plate, is_accredited, is_blacklisted, rating) VALUES
('ИП Перевозчиков Д.С.', 'А123ВС77', true,  false, 4.8),
('ООО "ГрузАвто"',       'В456ОР99', true,  false, 4.2),
('ИП Дальнобоев Н.К.',   'С789ТУ50', true,  true,  3.1),  -- в чёрном списке
('ООО "ТранспортСервис"','К111АА78', true,  false, 4.5),
('ИП Молчанов Р.И.',     'Е222ВВ23', false, false, 3.9);  -- не аккредитован

CREATE TABLE drivers (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL,
    carrier_id INT REFERENCES carriers(id)
);

INSERT INTO drivers (full_name, carrier_id) VALUES
('Иванов Сергей Петрович',    1),
('Петров Алексей Викторович', 1),
('Смирнов Дмитрий Олегович',  2),
('Кузнецов Андрей Сергеевич', 2),
('Васильев Игорь Николаевич', 3),
('Никитин Олег Васильевич',   4),
('Морозов Павел Андреевич',   4),
('Волков Артём Дмитриевич',   5);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INT REFERENCES customers(id),
    carrier_id INT REFERENCES carriers(id),
    driver_id INT REFERENCES drivers(id),
    origin_city_id INT REFERENCES cities(id),
    destination_city_id INT REFERENCES cities(id),
    weight_kg NUMERIC(10,2),
    volume_m3 NUMERIC(6,2),
    status VARCHAR(30) DEFAULT 'new',
    order_type VARCHAR(20),
    price NUMERIC(10,2),
    base_rate_with_vat NUMERIC(10,2),
    base_rate_without_vat NUMERIC(10,2),
    vehicle_category_id INT REFERENCES vehicle_categories(id),
    loading_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    deleted_at TIMESTAMP DEFAULT NULL  -- мягкое удаление → 410 Gone
);

INSERT INTO orders (customer_id, carrier_id, driver_id, origin_city_id, destination_city_id,
                    weight_kg, volume_m3, status, order_type, price,
                    base_rate_with_vat, base_rate_without_vat, vehicle_category_id, loading_date)
VALUES
(1, 1, 1, 1, 6, 5000.00,  20.00, 'new',        'auction', 45000.00,  45000.00,  37500.00, 1, CURRENT_DATE + 2),
(2, 2, 3, 2, 1, 12000.00, 45.00, 'in_transit',  'direct',  87000.00,  87000.00,  72500.00, 1, CURRENT_DATE - 5),
(3, 3, 5, 3, 5, 8000.00,  30.00, 'delivered',   'tender',  62000.00,  62000.00,  51667.00, 2, CURRENT_DATE - 20),
(4, 4, 6, 4, 2, 15000.00, 60.00, 'cancelled',   'auction', 110000.00, 110000.00, 91667.00, 1, CURRENT_DATE - 10),
(5, 1, 2, 5, 3, 3000.00,  12.00, 'new',         'direct',  28000.00,  28000.00,  23333.00, 3, CURRENT_DATE + 5),
(1, 4, 7, 1, 4, 9500.00,  38.00, 'in_transit',  'tender',  72000.00,  72000.00,  60000.00, 1, CURRENT_DATE - 3);

CREATE TABLE bids (
    id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(id),
    carrier_id INT REFERENCES carriers(id),
    bid_amount NUMERIC(10,2) NOT NULL,
    is_winner BOOLEAN DEFAULT false,
    submitted_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO bids (order_id, carrier_id, bid_amount, is_winner) VALUES
(1, 1, 43000.00, true),   -- победитель с минимальной ставкой
(1, 2, 47000.00, false),
(1, 4, 44500.00, false),
(4, 2, 105000.00, false),
(4, 3, 108000.00, false),
(4, 4, 110000.00, true);  -- победитель НЕ с минимальной ставкой (специально для теста)

CREATE TABLE invoices (
    id SERIAL PRIMARY KEY,
    order_id INT REFERENCES orders(id),
    amount NUMERIC(10,2),
    due_date DATE,
    paid_at DATE
);

INSERT INTO invoices (order_id, amount, due_date, paid_at) VALUES
(2, 87000.00, CURRENT_DATE + 9,  CURRENT_DATE - 2),  -- оплачен
(3, 62000.00, CURRENT_DATE - 6,  CURRENT_DATE - 12), -- оплачен
(5, 28000.00, CURRENT_DATE + 19, NULL),               -- не оплачен (ещё не просрочен)
(6, 72000.00, CURRENT_DATE - 3,  NULL);               -- просроченная задолженность
