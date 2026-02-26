#!/usr/bin/env python3
"""
Load CSV files from data/csv files/ and insert into the database using Prisma.
Run from project root. Requires: prisma generate, DATABASE_URL set, and migrations applied.
"""
import asyncio
import csv
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

# Add project root so prisma can be imported
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

try:
    from prisma import Prisma
    from prisma.models import (
        Category,
        Type,
        Size,
        Color,
        Gender,
        Brand,
        CcpaymentType,
        CcpaymentState,
        CcentryMethod,
        Customer,
        Employee,
        Ccpayment,
        CcpaymentCard,
        Product,
        Ticket,
        TicketItem,
    )
except (AttributeError, ImportError):
    print(
        "Prisma client not generated for this schema. Run from project root:\n\n"
        "  source venv/bin/activate   # or: source .venv/bin/activate\n"
        "  python -m prisma generate\n\n"
        "Then run this script again.",
        file=sys.stderr,
    )
    sys.exit(1)

DATA_DIR = PROJECT_ROOT / "data" / "csv files"


def parse_date(s: str):
    if not s or not s.strip():
        return None
    s = s.strip()
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


def load_csv(path: Path) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


async def main():
    if not DATA_DIR.is_dir():
        print(f"Data directory not found: {DATA_DIR}")
        sys.exit(1)

    prisma = Prisma()
    await prisma.connect()

    try:
        # --- Lookup / reference (no FKs) ---
        path = DATA_DIR / "category.csv"
        if path.exists():
            rows = load_csv(path)
            data = [{"id": int(r["CATEGORY_ID"]), "name": r["CATEGORY_NAME"]} for r in rows]
            count = await Category.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"Category: {count}")

        path = DATA_DIR / "type.csv"
        if path.exists():
            rows = load_csv(path)
            data = [
                {"id": int(r["TYPE_ID"]), "name": r["TYPE_NAME"], "categoryId": int(r["CATEGORY_ID"])}
                for r in rows
            ]
            count = await Type.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"Type: {count}")

        path = DATA_DIR / "size.csv"
        if path.exists():
            rows = load_csv(path)
            data = [
                {"code": r["SIZE_CODE"], "description": (r.get("DESCRIPTION") or "").strip() or None}
                for r in rows
            ]
            count = await Size.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"Size: {count}")

        path = DATA_DIR / "color.csv"
        if path.exists():
            rows = load_csv(path)
            data = [{"code": r["COLOR_CODE"], "name": r["COLOR_NAME"]} for r in rows]
            count = await Color.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"Color: {count}")

        path = DATA_DIR / "gender.csv"
        if path.exists():
            rows = load_csv(path)
            data = [{"id": int(r["GENDER_ID"]), "name": r["GENDER_NAME"]} for r in rows]
            count = await Gender.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"Gender: {count}")

        path = DATA_DIR / "brand.csv"
        if path.exists():
            rows = load_csv(path)
            data = [
                {
                    "id": int(r["BRAND_ID"]),
                    "name": r["BRAND_NAME"],
                    "email": (r.get("EMAIL") or "").strip() or None,
                }
                for r in rows
            ]
            count = await Brand.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"Brand: {count}")

        path = DATA_DIR / "ccpayment_type.csv"
        if path.exists():
            rows = load_csv(path)
            data = [
                {"code": r["CCTYPE"], "description": (r.get("DESCRIPTION") or "").strip() or None}
                for r in rows
            ]
            count = await CcpaymentType.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"CcpaymentType: {count}")

        path = DATA_DIR / "ccpayment_state.csv"
        if path.exists():
            rows = load_csv(path)
            data = [
                {"code": int(r["CCSTATE"]), "description": (r.get("DESCRIPTION") or "").strip() or None}
                for r in rows
            ]
            count = await CcpaymentState.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"CcpaymentState: {count}")

        path = DATA_DIR / "ccentry_method.csv"
        if path.exists():
            rows = load_csv(path)
            data = [
                {"code": int(r["CCMETHOD"]), "description": (r.get("DESCRIPTION") or "").strip() or None}
                for r in rows
            ]
            count = await CcentryMethod.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"CcentryMethod: {count}")

        # --- People ---
        path = DATA_DIR / "customer.csv"
        if path.exists():
            rows = load_csv(path)
            data = [
                {
                    "id": int(r["CUSTOMER_ID"]),
                    "firstname": r["FIRSTNAME"],
                    "lastname": r["LASTNAME"],
                    "dob": parse_date(r["DOB"]),
                    "email": (r.get("EMAIL") or "").strip() or None,
                    "phoneno": (r.get("PHONENO") or "").strip() or None,
                }
                for r in rows
            ]
            count = await Customer.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"Customer: {count}")

        path = DATA_DIR / "employee.csv"
        if path.exists():
            rows = load_csv(path)
            data = [
                {
                    "id": int(r["EMPLOYEE_ID"]),
                    "firstname": r["FIRSTNAME"],
                    "lastname": r["LASTNAME"],
                    "dob": parse_date(r["DOB"]),
                    "email": (r.get("EMAIL") or "").strip() or None,
                    "phoneno": (r.get("PHONENO") or "").strip() or None,
                }
                for r in rows
            ]
            count = await Employee.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"Employee: {count}")

        # --- Payments ---
        path = DATA_DIR / "ccpayment.csv"
        if path.exists():
            rows = load_csv(path)
            data = [
                {
                    "id": int(r["CCPAYMENT_ID"]),
                    "ccpayTranId": int(r["CCPAYTRAN_ID"]) if (r.get("CCPAYTRAN_ID") or "").strip() else None,
                    "expectedAmount": parse_decimal(r["EXPECTED_AMOUNT"]) or Decimal("0"),
                    "approvingAmount": parse_decimal(r["APPROVING_AMOUNT"]) or Decimal("0"),
                    "approvedAmount": parse_decimal(r["APPROVED_AMOUNT"]) or Decimal("0"),
                    "ccpaymentStateId": int(r["CCPAYMENT_STATE"]),
                    "timeCreated": parse_date(r["TIMECREATED"]),
                    "timeUpdated": parse_date(r["TIMEUPDATED"]),
                    "timeExpired": parse_date(r["TIMEEXPIRED"]),
                }
                for r in rows
            ]
            count = await Ccpayment.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"Ccpayment: {count}")

        path = DATA_DIR / "ccpayment_card.csv"
        if path.exists():
            rows = load_csv(path)
            data = [
                {
                    "paymentId": int(r["CCPAYMENT_ID"]),
                    "paymentTypeCode": r["PAYMENT_TYPE"],
                    "isEncrypt": (r.get("IS_ENCRYPT") or "").strip() or None,
                    "cardNumber": (r.get("CARD_NUMBER") or "").strip() or None,
                    "bankName": (r.get("BANKNAME") or "").strip() or None,
                    "ccExpDate": int(r["CCEXPDATE"]) if (r.get("CCEXPDATE") or "").strip() else None,
                    "ccentryMethodId": int(r["CCENTRY_METHOD"]),
                }
                for r in rows
            ]
            count = await CcpaymentCard.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"CcpaymentCard: {count}")

        # --- Product ---
        path = DATA_DIR / "product.csv"
        if path.exists():
            rows = load_csv(path)
            data = [
                {
                    "id": int(r["PRODUCT_ID"]),
                    "typeId": int(r["TYPE_ID"]),
                    "sizeCode": r["SIZE_CODE"],
                    "colorCode": r["COLOR_CODE"],
                    "name": r["PRODUCT_NAME"],
                    "brandId": int(r["BRAND_ID"]),
                    "genderId": int(r["GENDER_ID"]),
                    "description": (r.get("DESCRIPTION") or "").strip() or None,
                }
                for r in rows
            ]
            count = await Product.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"Product: {count}")

        # --- Ticket ---
        path = DATA_DIR / "ticket.csv"
        if path.exists():
            rows = load_csv(path)
            data = [
                {
                    "id": int(r["TICKET_ID"]),
                    "timePlaced": parse_date(r["TIMEPLACED"]),
                    "employeeId": int(r["EMPLOYEE_ID"]),
                    "customerId": int(r["CUSTOMER_ID"]),
                    "totalProduct": parse_decimal(r["TOTAL_PRODUCT"]) or Decimal("0"),
                    "totalTax": parse_decimal(r["TOTAL_TAX"]) or Decimal("0"),
                    "totalOrder": parse_decimal(r["TOTAL_ORDER"]) or Decimal("0"),
                    "ccpaymentId": int(r["CCPAYMENT_ID"]),
                }
                for r in rows
            ]
            count = await Ticket.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"Ticket: {count}")

        # --- TicketItem (composite key) ---
        path = DATA_DIR / "ticket_item.csv"
        if path.exists():
            rows = load_csv(path)
            data = [
                {
                    "ticketId": int(r["TICKET_ID"]),
                    "numSeq": int(r["NUMSEQ"]),
                    "productId": int(r["PRODUCT_ID"]),
                    "quantity": parse_decimal(r["QUANTITY"]) or Decimal("0"),
                    "price": parse_decimal(r["PRICE"]) or Decimal("0"),
                    "taxAmount": parse_decimal(r["TAX_AMOUNT"]) or Decimal("0"),
                    "productAmount": parse_decimal(r["PRODUCT_AMOUNT"]) or Decimal("0"),
                }
                for r in rows
            ]
            count = await TicketItem.prisma(prisma).create_many(data=data, skip_duplicates=True)
            print(f"TicketItem: {count}")

        print("Done.")
    finally:
        await prisma.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
