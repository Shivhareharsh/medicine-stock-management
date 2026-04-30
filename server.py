import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
SQL_DIR = BASE_DIR / "sql"
DB_PATH = BASE_DIR / "medicine_stock.db"


def dict_row(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


@contextmanager
def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = dict_row
    connection.execute("PRAGMA foreign_keys = ON;")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    schema_sql = (SQL_DIR / "schema.sql").read_text(encoding="utf-8")
    seed_sql = (SQL_DIR / "seed.sql").read_text(encoding="utf-8")
    with get_connection() as connection:
        connection.executescript(schema_sql)
        needs_seed = connection.execute("SELECT COUNT(*) AS count FROM medicines").fetchone()["count"] == 0
        if needs_seed:
            connection.executescript(seed_sql)


def json_response(handler, payload, status=HTTPStatus.OK):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(handler, text, status=HTTPStatus.OK, content_type="text/plain; charset=utf-8"):
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def parse_json_body(handler):
    content_length = int(handler.headers.get("Content-Length", 0))
    if content_length == 0:
        return {}
    raw = handler.rfile.read(content_length)
    return json.loads(raw.decode("utf-8"))


def today_iso():
    return date.today().isoformat()


def required_fields(payload, fields):
    missing = [field for field in fields if not str(payload.get(field, "")).strip()]
    if missing:
        raise ValueError(f"Missing fields: {', '.join(missing)}")


def get_or_create_lookup_id(connection, table, value):
    cursor = connection.execute(
        f"INSERT OR IGNORE INTO {table}(name) VALUES (?)",
        (value.strip(),),
    )
    if cursor.lastrowid:
        return cursor.lastrowid
    return connection.execute(
        f"SELECT id FROM {table} WHERE name = ?",
        (value.strip(),),
    ).fetchone()["id"]


def get_dashboard_data():
    with get_connection() as connection:
        totals = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM medicines) AS total_medicines,
                (SELECT COUNT(*) FROM suppliers) AS suppliers_count,
                (SELECT COALESCE(SUM(current_stock), 0) FROM medicines) AS stock_units,
                (SELECT COUNT(*) FROM medicine_inventory_view WHERE stock_status = 'LOW') AS low_stock_items,
                (
                    SELECT COUNT(*)
                    FROM expiring_batches_view
                    WHERE days_to_expiry BETWEEN 0 AND 60
                ) AS expiring_batches
            """
        ).fetchone()

        low_stock = connection.execute(
            """
            SELECT name, current_stock, reorder_level, stock_status
            FROM medicine_inventory_view
            WHERE stock_status IN ('LOW', 'OUT')
            ORDER BY
                CASE stock_status
                    WHEN 'OUT' THEN 1
                    ELSE 2
                END,
                current_stock ASC,
                name ASC
            LIMIT 6
            """
        ).fetchall()

        recent_transactions = connection.execute(
            """
            SELECT
                st.id,
                m.name AS medicine_name,
                pb.batch_no,
                st.transaction_type,
                st.quantity,
                st.reference_note,
                st.transaction_time
            FROM stock_transactions st
            JOIN medicines m ON m.id = st.medicine_id
            LEFT JOIN purchase_batches pb ON pb.id = st.batch_id
            ORDER BY st.transaction_time DESC, st.id DESC
            LIMIT 8
            """
        ).fetchall()

        top_dispensed = connection.execute(
            """
            SELECT
                m.name,
                COALESCE(SUM(CASE WHEN st.transaction_type = 'OUT' THEN st.quantity ELSE 0 END), 0) AS dispensed_units
            FROM medicines m
            LEFT JOIN stock_transactions st ON st.medicine_id = m.id
            GROUP BY m.id
            ORDER BY dispensed_units DESC, m.name ASC
            LIMIT 5
            """
        ).fetchall()

    return {
        "totals": totals,
        "low_stock": low_stock,
        "recent_transactions": recent_transactions,
        "top_dispensed": top_dispensed,
    }


def get_medicines(search="", stock_filter="ALL"):
    query = """
        SELECT
            medicine_id,
            sku,
            name,
            category_name,
            supplier_name,
            dosage_form,
            unit_price,
            reorder_level,
            current_stock,
            requires_prescription,
            nearest_expiry,
            stock_status
        FROM medicine_inventory_view
        WHERE (? = '' OR name LIKE ? OR sku LIKE ? OR supplier_name LIKE ? OR category_name LIKE ?)
          AND (? = 'ALL' OR stock_status = ?)
        ORDER BY
            CASE stock_status
                WHEN 'OUT' THEN 1
                WHEN 'LOW' THEN 2
                WHEN 'EXPIRING' THEN 3
                ELSE 4
            END,
            name ASC
    """
    like_value = f"%{search}%"
    with get_connection() as connection:
        return connection.execute(
            query,
            (search, like_value, like_value, like_value, like_value, stock_filter, stock_filter),
        ).fetchall()


def get_suppliers():
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT id, name, contact_person, phone, email, city
            FROM suppliers
            ORDER BY name ASC
            """
        ).fetchall()


def get_transactions(txn_type="ALL"):
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT
                st.id,
                m.name AS medicine_name,
                pb.batch_no,
                st.transaction_type,
                st.quantity,
                st.reference_note,
                st.transaction_time
            FROM stock_transactions st
            JOIN medicines m ON m.id = st.medicine_id
            LEFT JOIN purchase_batches pb ON pb.id = st.batch_id
            WHERE ? = 'ALL' OR st.transaction_type = ?
            ORDER BY st.transaction_time DESC, st.id DESC
            LIMIT 30
            """,
            (txn_type, txn_type),
        ).fetchall()


def create_medicine(payload):
    required_fields(
        payload,
        [
            "sku",
            "name",
            "category_name",
            "supplier_name",
            "dosage_form",
            "unit_price",
            "reorder_level",
        ],
    )

    with get_connection() as connection:
        category_id = get_or_create_lookup_id(connection, "medicine_categories", payload["category_name"])
        supplier_id = get_or_create_lookup_id(connection, "suppliers", payload["supplier_name"])

        connection.execute(
            """
            INSERT INTO medicines(
                sku, name, category_id, supplier_id, dosage_form, unit_price,
                reorder_level, current_stock, requires_prescription
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                payload["sku"].strip(),
                payload["name"].strip(),
                category_id,
                supplier_id,
                payload["dosage_form"].strip(),
                float(payload["unit_price"]),
                int(payload["reorder_level"]),
                1 if str(payload.get("requires_prescription", "")).lower() in {"1", "true", "yes", "on"} else 0,
            ),
        )


def create_supplier(payload):
    required_fields(payload, ["name", "contact_person", "phone", "email", "city"])
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO suppliers(name, contact_person, phone, email, city)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                payload["name"].strip(),
                payload["contact_person"].strip(),
                payload["phone"].strip(),
                payload["email"].strip(),
                payload["city"].strip(),
            ),
        )


def receive_stock(payload):
    required_fields(
        payload,
        [
            "medicine_id",
            "batch_no",
            "manufacture_date",
            "expiry_date",
            "quantity_received",
            "unit_cost",
        ],
    )

    received_on = payload.get("received_on", "").strip() or today_iso()

    with get_connection() as connection:
        connection.execute("BEGIN")
        connection.execute(
            """
            INSERT INTO purchase_batches(
                medicine_id, batch_no, manufacture_date, expiry_date,
                quantity_received, quantity_available, received_on, unit_cost
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(payload["medicine_id"]),
                payload["batch_no"].strip(),
                payload["manufacture_date"].strip(),
                payload["expiry_date"].strip(),
                int(payload["quantity_received"]),
                int(payload["quantity_received"]),
                received_on,
                float(payload["unit_cost"]),
            ),
        )


def dispense_medicine(payload):
    required_fields(payload, ["medicine_id", "quantity", "reference_note"])

    medicine_id = int(payload["medicine_id"])
    requested_quantity = int(payload["quantity"])
    note = payload["reference_note"].strip()

    if requested_quantity <= 0:
        raise ValueError("Quantity should be greater than zero.")

    with get_connection() as connection:
        connection.execute("BEGIN")
        medicine = connection.execute(
            """
            SELECT id, name, current_stock, requires_prescription
            FROM medicines
            WHERE id = ?
            """,
            (medicine_id,),
        ).fetchone()

        if not medicine:
            raise ValueError("Medicine not found.")
        if medicine["current_stock"] < requested_quantity:
            raise ValueError("Insufficient stock for the requested dispense quantity.")
        if medicine["requires_prescription"] and "rx" not in note.lower() and "prescription" not in note.lower():
            raise ValueError("Prescription medicines should include an Rx or prescription reference in the note.")

        remaining = requested_quantity
        batches = connection.execute(
            """
            SELECT id, batch_no, quantity_available
            FROM purchase_batches
            WHERE medicine_id = ? AND quantity_available > 0 AND expiry_date >= DATE('now')
            ORDER BY expiry_date ASC, received_on ASC, id ASC
            """,
            (medicine_id,),
        ).fetchall()

        if not batches:
            raise ValueError("No saleable batch is available for this medicine.")

        for batch in batches:
            if remaining == 0:
                break
            picked = min(remaining, batch["quantity_available"])
            connection.execute(
                """
                UPDATE purchase_batches
                SET quantity_available = quantity_available - ?
                WHERE id = ?
                """,
                (picked, batch["id"]),
            )
            connection.execute(
                """
                INSERT INTO stock_transactions(
                    medicine_id, batch_id, transaction_type, quantity, reference_note, transaction_time
                )
                VALUES (?, ?, 'OUT', ?, ?, CURRENT_TIMESTAMP)
                """,
                (medicine_id, batch["id"], picked, note),
            )
            remaining -= picked

        if remaining != 0:
            raise ValueError("Unable to fulfill the dispense request from available batches.")

        connection.execute(
            """
            UPDATE medicines
            SET current_stock = current_stock - ?
            WHERE id = ?
            """,
            (requested_quantity, medicine_id),
        )


class MedicineStockRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        params = parse_qs(parsed_url.query)

        try:
            if path == "/api/dashboard":
                return json_response(self, get_dashboard_data())
            if path == "/api/medicines":
                search = params.get("search", [""])[0]
                stock_filter = params.get("stock", ["ALL"])[0]
                return json_response(self, get_medicines(search, stock_filter))
            if path == "/api/suppliers":
                return json_response(self, get_suppliers())
            if path == "/api/transactions":
                txn_type = params.get("type", ["ALL"])[0]
                return json_response(self, get_transactions(txn_type))

            return self.serve_static(path)
        except sqlite3.IntegrityError as error:
            json_response(self, {"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except ValueError as error:
            json_response(self, {"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception as error:
            json_response(self, {"error": f"Unexpected server error: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        try:
            payload = parse_json_body(self)
            if path == "/api/medicines":
                create_medicine(payload)
                return json_response(self, {"message": "Medicine added successfully."}, HTTPStatus.CREATED)
            if path == "/api/suppliers":
                create_supplier(payload)
                return json_response(self, {"message": "Supplier added successfully."}, HTTPStatus.CREATED)
            if path == "/api/stock/receive":
                receive_stock(payload)
                return json_response(self, {"message": "Stock batch recorded successfully."}, HTTPStatus.CREATED)
            if path == "/api/stock/dispense":
                dispense_medicine(payload)
                return json_response(self, {"message": "Medicine dispensed successfully."}, HTTPStatus.CREATED)

            json_response(self, {"error": "Route not found."}, HTTPStatus.NOT_FOUND)
        except sqlite3.IntegrityError as error:
            json_response(self, {"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except ValueError as error:
            json_response(self, {"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except Exception as error:
            json_response(self, {"error": f"Unexpected server error: {error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def serve_static(self, path):
        safe_path = path.lstrip("/") or "index.html"
        target = STATIC_DIR / safe_path
        if path == "/" or not target.exists() or target.is_dir():
            target = STATIC_DIR / "index.html"
        if not target.exists():
            return text_response(self, "Not found", HTTPStatus.NOT_FOUND)

        suffix_map = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }
        content_type = suffix_map.get(target.suffix, "application/octet-stream")
        text_response(self, target.read_text(encoding="utf-8"), content_type=content_type)

    def log_message(self, fmt, *args):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} - {fmt % args}")


def run():
    initialize_database()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), MedicineStockRequestHandler)
    print("MediTrack Pharmacy Stock Management System running at http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    run()
