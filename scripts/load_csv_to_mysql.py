#!/usr/bin/env python3
"""
Load all CSV files from data/csv files/ into the MySQL database.
Run from project root. Requires MySQL running (e.g. docker-compose mysql service).

Usage:
  python scripts/load_csv_to_mysql.py   # create tables if missing, then insert all CSV data

Connection: defaults match docker-compose (host 127.0.0.1, port 3308, db ai-fashiondb).
Override with MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE.
"""
import csv
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "csv files"


def get_mysql_config() -> Dict[str, Any]:
    return {
        "host": os.environ.get("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.environ.get("MYSQL_PORT", "3308")),
        "user": os.environ.get("MYSQL_USER", "ai-fashion-user"),
        "password": os.environ.get("MYSQL_PASSWORD", "ai-fashion-pass"),
        "database": os.environ.get("MYSQL_DATABASE", "ai-fashiondb"),
        "charset": "utf8mb4",
    }


def parse_date(s: str) -> Optional[datetime]:
    if not s or not str(s).strip():
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {s!r}")


def parse_decimal(s: str) -> Optional[Decimal]:
    if s is None or (isinstance(s, str) and not s.strip()):
        return None
    return Decimal(str(s).strip())


def _opt_str(r: Dict[str, str], key: str) -> Optional[str]:
    v = (r.get(key) or "").strip()
    return v or None


def load_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def create_tables(conn) -> None:
    """Create the 15 CSV-related tables if they do not exist (MySQL DDL)."""
    cursor = conn.cursor()
    ddl = [
        """CREATE TABLE IF NOT EXISTS category (
            id INT NOT NULL PRIMARY KEY,
            category_name VARCHAR(255) NOT NULL
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS type (
            id INT NOT NULL PRIMARY KEY,
            type_name VARCHAR(255) NOT NULL,
            category_id INT NOT NULL,
            INDEX (category_id)
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS size (
            code VARCHAR(31) NOT NULL PRIMARY KEY,
            description VARCHAR(255) NULL
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS color (
            code VARCHAR(31) NOT NULL PRIMARY KEY,
            color_name VARCHAR(255) NOT NULL
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS gender (
            id INT NOT NULL PRIMARY KEY,
            gender_name VARCHAR(255) NOT NULL
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS brand (
            id INT NOT NULL PRIMARY KEY,
            brand_name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NULL
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS ccpayment_type (
            code VARCHAR(31) NOT NULL PRIMARY KEY,
            description VARCHAR(255) NULL
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS ccpayment_state (
            code INT NOT NULL PRIMARY KEY,
            description VARCHAR(255) NULL
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS ccentry_method (
            code INT NOT NULL PRIMARY KEY,
            description VARCHAR(255) NULL
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS customer (
            id INT NOT NULL PRIMARY KEY,
            firstname VARCHAR(255) NOT NULL,
            lastname VARCHAR(255) NOT NULL,
            dob DATE NOT NULL,
            email VARCHAR(255) NULL,
            phoneno VARCHAR(255) NULL
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS employee (
            id INT NOT NULL PRIMARY KEY,
            firstname VARCHAR(255) NOT NULL,
            lastname VARCHAR(255) NOT NULL,
            dob DATE NOT NULL,
            email VARCHAR(255) NULL,
            phoneno VARCHAR(255) NULL
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS ccpayment (
            id BIGINT NOT NULL PRIMARY KEY,
            ccpaytran_id BIGINT NULL,
            expected_amount DECIMAL(18,5) NOT NULL,
            approving_amount DECIMAL(18,5) NOT NULL,
            approved_amount DECIMAL(18,5) NOT NULL,
            ccpayment_state INT NOT NULL,
            timecreated DATETIME NOT NULL,
            timeupdated DATETIME NOT NULL,
            timeexpired DATETIME NOT NULL,
            INDEX (ccpayment_state)
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS ccpayment_card (
            ccpayment_id BIGINT NOT NULL PRIMARY KEY,
            payment_type VARCHAR(31) NOT NULL,
            is_encrypt VARCHAR(31) NULL,
            card_number VARCHAR(255) NULL,
            bankname VARCHAR(255) NULL,
            ccexpdate INT NULL,
            ccentry_method INT NOT NULL,
            INDEX (payment_type),
            INDEX (ccentry_method)
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS product (
            id INT NOT NULL PRIMARY KEY,
            type_id INT NOT NULL,
            size_code VARCHAR(31) NOT NULL,
            color_code VARCHAR(31) NOT NULL,
            product_name VARCHAR(255) NOT NULL,
            brand_id INT NOT NULL,
            gender_id INT NOT NULL,
            description TEXT NULL,
            INDEX (type_id),
            INDEX (size_code),
            INDEX (color_code),
            INDEX (brand_id),
            INDEX (gender_id)
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS ticket (
            id BIGINT NOT NULL PRIMARY KEY,
            timeplaced DATETIME NOT NULL,
            employee_id INT NOT NULL,
            customer_id INT NOT NULL,
            total_product DECIMAL(18,5) NOT NULL,
            total_tax DECIMAL(18,5) NOT NULL,
            total_order DECIMAL(18,5) NOT NULL,
            ccpayment_id BIGINT NOT NULL,
            INDEX (employee_id),
            INDEX (customer_id),
            INDEX (ccpayment_id),
            INDEX (timeplaced)
        ) DEFAULT CHARSET=utf8mb4""",
        """CREATE TABLE IF NOT EXISTS ticket_item (
            ticket_id BIGINT NOT NULL,
            numseq INT NOT NULL,
            product_id INT NOT NULL,
            quantity DECIMAL(18,5) NOT NULL,
            price DECIMAL(18,5) NOT NULL,
            tax_amount DECIMAL(18,5) NOT NULL,
            product_amount DECIMAL(18,5) NOT NULL,
            PRIMARY KEY (ticket_id, numseq),
            INDEX (product_id)
        ) DEFAULT CHARSET=utf8mb4""",
    ]
    for stmt in ddl:
        cursor.execute(stmt)
    cursor.close()
    conn.commit()
    print("Tables created or already exist.")


def load_all(conn, data_dir: Path) -> None:
    cursor = conn.cursor()
    total_inserted = 0

    # --- category ---
    path = data_dir / "category.csv"
    if not path.exists():
        print(f"Skip category: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            cursor.execute(
                "INSERT IGNORE INTO category (id, category_name) VALUES (%s, %s)",
                (int(r["CATEGORY_ID"]), r["CATEGORY_NAME"]),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"category: {n}")

    # --- type ---
    path = data_dir / "type.csv"
    if not path.exists():
        print(f"Skip type: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            cursor.execute(
                "INSERT IGNORE INTO type (id, type_name, category_id) VALUES (%s, %s, %s)",
                (int(r["TYPE_ID"]), r["TYPE_NAME"], int(r["CATEGORY_ID"])),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"type: {n}")

    # --- size ---
    path = data_dir / "size.csv"
    if not path.exists():
        print(f"Skip size: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            cursor.execute(
                "INSERT IGNORE INTO size (code, description) VALUES (%s, %s)",
                (r["SIZE_CODE"], _opt_str(r, "DESCRIPTION")),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"size: {n}")

    # --- color ---
    path = data_dir / "color.csv"
    if not path.exists():
        print(f"Skip color: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            cursor.execute(
                "INSERT IGNORE INTO color (code, color_name) VALUES (%s, %s)",
                (r["COLOR_CODE"], r["COLOR_NAME"]),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"color: {n}")

    # --- gender ---
    path = data_dir / "gender.csv"
    if not path.exists():
        print(f"Skip gender: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            cursor.execute(
                "INSERT IGNORE INTO gender (id, gender_name) VALUES (%s, %s)",
                (int(r["GENDER_ID"]), r["GENDER_NAME"]),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"gender: {n}")

    # --- brand ---
    path = data_dir / "brand.csv"
    if not path.exists():
        print(f"Skip brand: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            cursor.execute(
                "INSERT IGNORE INTO brand (id, brand_name, email) VALUES (%s, %s, %s)",
                (int(r["BRAND_ID"]), r["BRAND_NAME"], _opt_str(r, "EMAIL")),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"brand: {n}")

    # --- ccpayment_type ---
    path = data_dir / "ccpayment_type.csv"
    if not path.exists():
        print(f"Skip ccpayment_type: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            cursor.execute(
                "INSERT IGNORE INTO ccpayment_type (code, description) VALUES (%s, %s)",
                (r["CCTYPE"], _opt_str(r, "DESCRIPTION")),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"ccpayment_type: {n}")

    # --- ccpayment_state ---
    path = data_dir / "ccpayment_state.csv"
    if not path.exists():
        print(f"Skip ccpayment_state: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            cursor.execute(
                "INSERT IGNORE INTO ccpayment_state (code, description) VALUES (%s, %s)",
                (int(r["CCSTATE"]), _opt_str(r, "DESCRIPTION")),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"ccpayment_state: {n}")

    # --- ccentry_method ---
    path = data_dir / "ccentry_method.csv"
    if not path.exists():
        print(f"Skip ccentry_method: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            cursor.execute(
                "INSERT IGNORE INTO ccentry_method (code, description) VALUES (%s, %s)",
                (int(r["CCMETHOD"]), _opt_str(r, "DESCRIPTION")),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"ccentry_method: {n}")

    # --- customer ---
    path = data_dir / "customer.csv"
    if not path.exists():
        print(f"Skip customer: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            dob = parse_date(r["DOB"])
            cursor.execute(
                "INSERT IGNORE INTO customer (id, firstname, lastname, dob, email, phoneno) VALUES (%s, %s, %s, %s, %s, %s)",
                (int(r["CUSTOMER_ID"]), r["FIRSTNAME"], r["LASTNAME"], dob, _opt_str(r, "EMAIL"), _opt_str(r, "PHONENO")),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"customer: {n}")

    # --- employee ---
    path = data_dir / "employee.csv"
    if not path.exists():
        print(f"Skip employee: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            dob = parse_date(r["DOB"])
            cursor.execute(
                "INSERT IGNORE INTO employee (id, firstname, lastname, dob, email, phoneno) VALUES (%s, %s, %s, %s, %s, %s)",
                (int(r["EMPLOYEE_ID"]), r["FIRSTNAME"], r["LASTNAME"], dob, _opt_str(r, "EMAIL"), _opt_str(r, "PHONENO")),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"employee: {n}")

    # --- ccpayment ---
    path = data_dir / "ccpayment.csv"
    if not path.exists():
        print(f"Skip ccpayment: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            ccpaytran = int(r["CCPAYTRAN_ID"]) if (r.get("CCPAYTRAN_ID") or "").strip() else None
            cursor.execute(
                """INSERT IGNORE INTO ccpayment (
                    id, ccpaytran_id, expected_amount, approving_amount, approved_amount,
                    ccpayment_state, timecreated, timeupdated, timeexpired
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    int(r["CCPAYMENT_ID"]),
                    ccpaytran,
                    parse_decimal(r["EXPECTED_AMOUNT"]) or Decimal("0"),
                    parse_decimal(r["APPROVING_AMOUNT"]) or Decimal("0"),
                    parse_decimal(r["APPROVED_AMOUNT"]) or Decimal("0"),
                    int(r["CCPAYMENT_STATE"]),
                    parse_date(r["TIMECREATED"]),
                    parse_date(r["TIMEUPDATED"]),
                    parse_date(r["TIMEEXPIRED"]),
                ),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"ccpayment: {n}")

    # --- ccpayment_card ---
    path = data_dir / "ccpayment_card.csv"
    if not path.exists():
        print(f"Skip ccpayment_card: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            cc_exp = int(r["CCEXPDATE"]) if (r.get("CCEXPDATE") or "").strip() else None
            cursor.execute(
                """INSERT IGNORE INTO ccpayment_card (
                    ccpayment_id, payment_type, is_encrypt, card_number, bankname, ccexpdate, ccentry_method
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    int(r["CCPAYMENT_ID"]),
                    r["PAYMENT_TYPE"],
                    _opt_str(r, "IS_ENCRYPT"),
                    _opt_str(r, "CARD_NUMBER"),
                    _opt_str(r, "BANKNAME"),
                    cc_exp,
                    int(r["CCENTRY_METHOD"]),
                ),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"ccpayment_card: {n}")

    # --- product ---
    path = data_dir / "product.csv"
    if not path.exists():
        print(f"Skip product: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            cursor.execute(
                """INSERT IGNORE INTO product (
                    id, type_id, size_code, color_code, product_name, brand_id, gender_id, description
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    int(r["PRODUCT_ID"]),
                    int(r["TYPE_ID"]),
                    r["SIZE_CODE"],
                    r["COLOR_CODE"],
                    r["PRODUCT_NAME"],
                    int(r["BRAND_ID"]),
                    int(r["GENDER_ID"]),
                    _opt_str(r, "DESCRIPTION"),
                ),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"product: {n}")

    # --- ticket ---
    path = data_dir / "ticket.csv"
    if not path.exists():
        print(f"Skip ticket: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            cursor.execute(
                """INSERT IGNORE INTO ticket (
                    id, timeplaced, employee_id, customer_id, total_product, total_tax, total_order, ccpayment_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    int(r["TICKET_ID"]),
                    parse_date(r["TIMEPLACED"]),
                    int(r["EMPLOYEE_ID"]),
                    int(r["CUSTOMER_ID"]),
                    parse_decimal(r["TOTAL_PRODUCT"]) or Decimal("0"),
                    parse_decimal(r["TOTAL_TAX"]) or Decimal("0"),
                    parse_decimal(r["TOTAL_ORDER"]) or Decimal("0"),
                    int(r["CCPAYMENT_ID"]),
                ),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"ticket: {n}")

    # --- ticket_item ---
    path = data_dir / "ticket_item.csv"
    if not path.exists():
        print(f"Skip ticket_item: {path} not found")
    else:
        rows = load_csv(path)
        n = 0
        for r in rows:
            cursor.execute(
                """INSERT IGNORE INTO ticket_item (
                    ticket_id, numseq, product_id, quantity, price, tax_amount, product_amount
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (
                    int(r["TICKET_ID"]),
                    int(r["NUMSEQ"]),
                    int(r["PRODUCT_ID"]),
                    parse_decimal(r["QUANTITY"]) or Decimal("0"),
                    parse_decimal(r["PRICE"]) or Decimal("0"),
                    parse_decimal(r["TAX_AMOUNT"]) or Decimal("0"),
                    parse_decimal(r["PRODUCT_AMOUNT"]) or Decimal("0"),
                ),
            )
            n += cursor.rowcount
        total_inserted += n
        print(f"ticket_item: {n}")

    cursor.close()
    conn.commit()
    print(f"Done. Total rows inserted: {total_inserted}")


def main() -> None:
    if not DATA_DIR.is_dir():
        print(f"Data directory not found: {DATA_DIR}", file=sys.stderr)
        sys.exit(1)

    try:
        import pymysql
    except ImportError:
        print("PyMySQL is required. Install with: pip install pymysql", file=sys.stderr)
        sys.exit(1)

    config = get_mysql_config()
    try:
        conn = pymysql.connect(**config)
    except Exception as e:
        print(f"Cannot connect to MySQL: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        # Always ensure tables exist (CREATE TABLE IF NOT EXISTS) so one run works
        create_tables(conn)
        load_all(conn, DATA_DIR)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
