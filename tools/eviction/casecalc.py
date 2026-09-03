"""Ledger allocation + claim math for the NC summary ejectment packet.

Payments are applied to the OLDEST outstanding charge first (as the ledger does).
The rent ask through the court date is:

    rent ask = (unpaid rent from prior months)
             + max(0, rent accrued through hearing date - payments applied to that month's rent)

Late fees and add-on fees are deliberately excluded from the money ask.
"""
from datetime import date, datetime

def money(n):
    try:
        return "${:,.2f}".format(float(n))
    except Exception:
        return "$0.00"

def _d(v):
    """Parse a date from several plausible formats; return None if unknown."""
    if isinstance(v, date):
        return v
    if not v:
        return None
    s = str(v).strip()
    for fmt in ("%m-%d-%Y", "%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m-%d-%y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def allocate(rows):
    """Apply payments to the oldest outstanding charge first.

    rows: [{date, item, amount, type: 'charge'|'payment', kind: 'rent'|'fee'|'cost'}]
    Returns (charges, allocations, unapplied) where charges carry a 'remaining'.
    """
    charges, payments = [], []
    for r in rows or []:
        amt = float(r.get("amount") or 0)
        if amt == 0:
            continue
        item = dict(r)
        item["_date"] = _d(r.get("date"))
        # A payment may be flagged type="payment" OR entered as a negative amount
        # (the ledger convention where rows reconcile to the balance).
        is_payment = (r.get("type") or "").lower() == "payment" or amt < 0
        if is_payment:
            item["amount"] = abs(amt)
            payments.append(item)
        else:
            item["remaining"] = amt
            charges.append(item)
    far = date(2100, 1, 1)
    charges.sort(key=lambda c: (c["_date"] or far))
    payments.sort(key=lambda p: (p["_date"] or far))

    allocations, unapplied = [], 0.0
    for pmt in payments:
        left = float(pmt.get("amount") or 0)
        for c in charges:
            if left <= 0.004:
                break
            if c["remaining"] <= 0.004:
                continue
            take = min(left, c["remaining"])
            c["remaining"] = round(c["remaining"] - take, 2)
            left = round(left - take, 2)
            allocations.append({
                "payment_date": pmt.get("date"), "amount": round(take, 2),
                "applied_to": c.get("item"), "charge_date": c.get("date"),
                "kind": (c.get("kind") or "").lower(),
            })
        if left > 0.004:
            unapplied = round(unapplied + left, 2)
    return charges, allocations, unapplied

def compute(case):
    """Return the derived numbers the packet needs."""
    rent = case.get("rent") or {}
    claim = case.get("claim") or {}
    ledger = case.get("ledger") or {}

    monthly = float(rent.get("monthly") or 0)
    days_in_month = int(claim.get("daysInMonth") or 30) or 30
    prorated_days = int(claim.get("proratedDays") or 0)
    daily = monthly / days_in_month if days_in_month else 0.0
    accrued = round(daily * prorated_days, 2)

    charges, allocations, unapplied = allocate(ledger.get("rows"))
    due = _d(claim.get("rentDueDate"))

    # split rent charges into the claim month vs earlier unpaid rent
    current_paid = 0.0
    prior_rent_unpaid = 0.0
    for c in charges:
        if (c.get("kind") or "").lower() != "rent":
            continue
        cd = c.get("_date")
        if due and cd and cd < due:
            prior_rent_unpaid = round(prior_rent_unpaid + c["remaining"], 2)
        else:
            current_paid = round(current_paid + (float(c.get("amount") or 0) - c["remaining"]), 2)

    current_ask = round(max(0.0, accrued - current_paid), 2)
    rent_ask = round(prior_rent_unpaid + current_ask, 2)

    # Month basis: what is still owed on the whole month's rent charge
    # (charged - paid). Shown as the alternative if the magistrate awards the
    # full month rather than rent accrued through the court date.
    rent_charged = 0.0
    for c in charges:
        if (c.get("kind") or "").lower() != "rent":
            continue
        cd = c.get("_date")
        if not (due and cd and cd < due):
            rent_charged = round(rent_charged + float(c.get("amount") or 0), 2)
    if not rent_charged:
        rent_charged = monthly
    month_unpaid = round(max(0.0, rent_charged - current_paid), 2)
    month_basis_ask = round(prior_rent_unpaid + month_unpaid, 2)

    court_costs = case.get("courtCosts") or []
    costs_total = round(sum(float(c.get("amount") or 0) for c in court_costs), 2)
    costs_breakdown = " + ".join(
        "%s %s" % (c.get("label"), money(c.get("amount"))) for c in court_costs) or "—"

    fees_outstanding = round(sum(
        c["remaining"] for c in charges if (c.get("kind") or "").lower() in ("fee", "other")), 2)

    payments_total = round(sum(a["amount"] for a in allocations) + unapplied, 2)
    charge_sum = round(sum(float(c.get("amount") or 0) for c in charges), 2)
    stated_balance = ledger.get("balance")
    computed_balance = round(charge_sum - payments_total, 2)
    mismatch = None
    if stated_balance is not None:
        try:
            if abs(float(stated_balance) - computed_balance) > 0.005:
                mismatch = ("Ledger rows net to %s but the stated balance is %s — verify the ledger."
                            % (money(computed_balance), money(stated_balance)))
        except Exception:
            pass

    return {
        "money": money,
        "monthly": monthly, "daily": daily, "accrued": accrued,
        "prorated_days": prorated_days, "days_in_month": days_in_month,
        "current_paid": current_paid, "prior_rent_unpaid": prior_rent_unpaid,
        "rent_ask": rent_ask, "costs_total": costs_total,
        "rent_charged": rent_charged, "month_unpaid": month_unpaid,
        "month_basis_ask": month_basis_ask,
        "MONTHASK": money(month_basis_ask), "CHARGED": money(rent_charged),
        "PAID": money(current_paid),
        "costs_breakdown": costs_breakdown, "total_ask": round(rent_ask + costs_total, 2),
        "fees_outstanding": fees_outstanding,
        "allocations": allocations, "unapplied": unapplied,
        "has_payments": bool(allocations or unapplied),
        "computed_balance": computed_balance, "mismatch": mismatch,
        "D": money(daily), "ACCRUED": money(accrued), "FULL": money(monthly),
        "PRO": money(rent_ask), "COSTS": money(costs_total), "TOTAL": money(rent_ask + costs_total),
    }
