INSERT OR IGNORE INTO medicine_categories(name) VALUES
('Analgesics'),
('Antibiotics'),
('Cardiology'),
('Diabetes Care'),
('Respiratory');

INSERT OR IGNORE INTO suppliers(name, contact_person, phone, email, city) VALUES
('HealthBridge Pharma', 'Riya Kapoor', '9876541001', 'riya@healthbridge.example', 'Delhi'),
('Nova Medisupply', 'Karan Mehta', '9876541002', 'karan@novamedi.example', 'Mumbai'),
('CareAxis Distributors', 'Ananya Iyer', '9876541003', 'ananya@careaxis.example', 'Bengaluru'),
('VitaServe Labs', 'Aditya Rao', '9876541004', 'aditya@vitaserve.example', 'Hyderabad');

INSERT OR IGNORE INTO medicines(
    sku, name, category_id, supplier_id, dosage_form, unit_price, reorder_level, current_stock, requires_prescription
) VALUES
('MED-PCM-500', 'Paracetamol 500mg', 1, 1, 'Tablet', 2.50, 80, 0, 0),
('MED-AMX-250', 'Amoxicillin 250mg', 2, 2, 'Capsule', 6.75, 60, 0, 1),
('MED-ATR-10', 'Atorvastatin 10mg', 3, 3, 'Tablet', 14.40, 40, 0, 1),
('MED-MTF-500', 'Metformin 500mg', 4, 4, 'Tablet', 5.20, 70, 0, 1),
('MED-SLB-100', 'Salbutamol Syrup', 5, 1, 'Syrup', 48.00, 24, 0, 0);

INSERT OR IGNORE INTO purchase_batches(
    medicine_id, batch_no, manufacture_date, expiry_date, quantity_received, quantity_available, received_on, unit_cost
) VALUES
(1, 'PCM2401A', DATE('now', '-120 day'), DATE('now', '+220 day'), 240, 240, DATE('now', '-30 day'), 1.30),
(2, 'AMX2402B', DATE('now', '-110 day'), DATE('now', '+70 day'), 140, 140, DATE('now', '-26 day'), 4.20),
(3, 'ATR2403C', DATE('now', '-95 day'), DATE('now', '+160 day'), 90, 90, DATE('now', '-20 day'), 9.90),
(4, 'MTF2401D', DATE('now', '-140 day'), DATE('now', '+45 day'), 180, 180, DATE('now', '-16 day'), 3.10),
(5, 'SLB2404E', DATE('now', '-80 day'), DATE('now', '+25 day'), 42, 42, DATE('now', '-10 day'), 30.00);

UPDATE purchase_batches SET quantity_available = quantity_available - 170 WHERE medicine_id = 1;
UPDATE medicines SET current_stock = current_stock - 170 WHERE id = 1;
INSERT INTO stock_transactions(medicine_id, batch_id, transaction_type, quantity, reference_note, transaction_time)
VALUES (1, 1, 'OUT', 170, 'OPD bulk usage log', DATETIME('now', '-6 day'));

UPDATE purchase_batches SET quantity_available = quantity_available - 95 WHERE medicine_id = 2;
UPDATE medicines SET current_stock = current_stock - 95 WHERE id = 2;
INSERT INTO stock_transactions(medicine_id, batch_id, transaction_type, quantity, reference_note, transaction_time)
VALUES (2, 2, 'OUT', 95, 'Rx #AMX-7743', DATETIME('now', '-4 day'));

UPDATE purchase_batches SET quantity_available = quantity_available - 58 WHERE medicine_id = 4;
UPDATE medicines SET current_stock = current_stock - 58 WHERE id = 4;
INSERT INTO stock_transactions(medicine_id, batch_id, transaction_type, quantity, reference_note, transaction_time)
VALUES (4, 4, 'OUT', 58, 'Diabetes clinic issue', DATETIME('now', '-3 day'));

UPDATE purchase_batches SET quantity_available = quantity_available - 22 WHERE medicine_id = 5;
UPDATE medicines SET current_stock = current_stock - 22 WHERE id = 5;
INSERT INTO stock_transactions(medicine_id, batch_id, transaction_type, quantity, reference_note, transaction_time)
VALUES (5, 5, 'OUT', 22, 'Ward transfer note', DATETIME('now', '-2 day'));
