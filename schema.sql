PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS medicine_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    contact_person TEXT,
    phone TEXT UNIQUE,
    email TEXT UNIQUE,
    city TEXT
);

CREATE TABLE IF NOT EXISTS medicines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category_id INTEGER NOT NULL,
    supplier_id INTEGER NOT NULL,
    dosage_form TEXT NOT NULL,
    unit_price REAL NOT NULL CHECK (unit_price >= 0),
    reorder_level INTEGER NOT NULL DEFAULT 0 CHECK (reorder_level >= 0),
    current_stock INTEGER NOT NULL DEFAULT 0 CHECK (current_stock >= 0),
    requires_prescription INTEGER NOT NULL DEFAULT 0 CHECK (requires_prescription IN (0, 1)),
    FOREIGN KEY (category_id) REFERENCES medicine_categories(id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
);

CREATE TABLE IF NOT EXISTS purchase_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    medicine_id INTEGER NOT NULL,
    batch_no TEXT NOT NULL,
    manufacture_date TEXT NOT NULL,
    expiry_date TEXT NOT NULL,
    quantity_received INTEGER NOT NULL CHECK (quantity_received > 0),
    quantity_available INTEGER NOT NULL CHECK (quantity_available >= 0 AND quantity_available <= quantity_received),
    received_on TEXT NOT NULL,
    unit_cost REAL NOT NULL CHECK (unit_cost >= 0),
    FOREIGN KEY (medicine_id) REFERENCES medicines(id),
    UNIQUE (medicine_id, batch_no)
);

CREATE TABLE IF NOT EXISTS stock_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    medicine_id INTEGER NOT NULL,
    batch_id INTEGER,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('IN', 'OUT', 'ADJUSTMENT')),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    reference_note TEXT,
    transaction_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (medicine_id) REFERENCES medicines(id),
    FOREIGN KEY (batch_id) REFERENCES purchase_batches(id)
);

CREATE INDEX IF NOT EXISTS idx_medicines_name ON medicines(name);
CREATE INDEX IF NOT EXISTS idx_medicines_sku ON medicines(sku);
CREATE INDEX IF NOT EXISTS idx_batches_expiry ON purchase_batches(expiry_date);
CREATE INDEX IF NOT EXISTS idx_stock_transactions_type_time ON stock_transactions(transaction_type, transaction_time);

CREATE VIEW IF NOT EXISTS medicine_inventory_view AS
SELECT
    m.id AS medicine_id,
    m.sku,
    m.name,
    c.name AS category_name,
    s.name AS supplier_name,
    m.dosage_form,
    m.unit_price,
    m.reorder_level,
    m.current_stock,
    m.requires_prescription,
    (
        SELECT MIN(pb.expiry_date)
        FROM purchase_batches pb
        WHERE pb.medicine_id = m.id AND pb.quantity_available > 0
    ) AS nearest_expiry,
    CASE
        WHEN m.current_stock = 0 THEN 'OUT'
        WHEN m.current_stock <= m.reorder_level THEN 'LOW'
        WHEN (
            SELECT MIN(pb.expiry_date)
            FROM purchase_batches pb
            WHERE pb.medicine_id = m.id AND pb.quantity_available > 0
        ) IS NOT NULL
             AND (
                julianday((
                    SELECT MIN(pb.expiry_date)
                    FROM purchase_batches pb
                    WHERE pb.medicine_id = m.id AND pb.quantity_available > 0
                )) - julianday(DATE('now'))
             ) <= 45 THEN 'EXPIRING'
        ELSE 'SAFE'
    END AS stock_status
FROM medicines m
JOIN medicine_categories c ON c.id = m.category_id
JOIN suppliers s ON s.id = m.supplier_id;

CREATE VIEW IF NOT EXISTS expiring_batches_view AS
SELECT
    pb.id AS batch_id,
    m.name AS medicine_name,
    pb.batch_no,
    pb.expiry_date,
    pb.quantity_available,
    CAST(julianday(pb.expiry_date) - julianday(DATE('now')) AS INTEGER) AS days_to_expiry
FROM purchase_batches pb
JOIN medicines m ON m.id = pb.medicine_id
WHERE pb.quantity_available > 0;

CREATE TRIGGER IF NOT EXISTS trg_validate_batch_dates
BEFORE INSERT ON purchase_batches
FOR EACH ROW
BEGIN
    SELECT CASE
        WHEN DATE(NEW.expiry_date) <= DATE(NEW.manufacture_date)
        THEN RAISE(ABORT, 'Expiry date must be after manufacture date.')
    END;
END;

CREATE TRIGGER IF NOT EXISTS trg_after_batch_insert
AFTER INSERT ON purchase_batches
FOR EACH ROW
BEGIN
    UPDATE medicines
    SET current_stock = current_stock + NEW.quantity_received
    WHERE id = NEW.medicine_id;

    INSERT INTO stock_transactions(medicine_id, batch_id, transaction_type, quantity, reference_note, transaction_time)
    VALUES (NEW.medicine_id, NEW.id, 'IN', NEW.quantity_received, 'Stock received into inventory', CURRENT_TIMESTAMP);
END;
