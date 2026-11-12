"""Double-entry ledger. Every money event is a transaction (tx_key) whose DEBIT lines equal its CREDIT lines, in whole FCFA.

Accounts and what each money event does (P = price paid, C = commission, S = P - C):

  customer payment succeeds   DEBIT collection P | CREDIT platform_revenue C | CREDIT artisan_pending S      (split model)
                              DEBIT collection P | CREDIT artisan_pending P                                   (artisan-upfront model)
  artisan fee succeeds        DEBIT collection F | CREDIT platform_revenue F
  payout paid to the artisan  DEBIT artisan_pending S | CREDIT artisan_paid S
  refund requested            DEBIT platform_revenue C, artisan_pending S | CREDIT refund_payable P
  fee refund requested        DEBIT platform_revenue F | CREDIT refund_payable F

`collection` and `artisan_paid` together describe the provider side: gross money collected, and money sent out to artisans.
Posting is idempotent: a tx_key that already exists is skipped, so replaying an event can never double-credit.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import LedgerAccount, LedgerEntry, Payment, PaymentType, Payout
from app.config import get_settings
from app.services import payment_service

DEBIT, CREDIT = "DEBIT", "CREDIT"
ACCOUNTS = tuple(a.value for a in LedgerAccount)
FEE_TYPES = (PaymentType.COMMISSION.value, PaymentType.ASSIGNMENT_FEE.value)
Line = tuple[str, str, int]   # (account, direction, amount)


class LedgerError(Exception):
    """Raised when someone tries to post an unbalanced or invalid transaction. A bug, never a user error."""


def post(db: Session, tx_key: str, lines: list[Line], payment_id: uuid.UUID | None = None,
         payout_id: uuid.UUID | None = None) -> bool:
    """Post one balanced transaction. Returns False (and does nothing) if tx_key was already posted."""
    for account, direction, amount in lines:
        if account not in ACCOUNTS or direction not in (DEBIT, CREDIT):
            raise LedgerError(f"invalid ledger line {account}/{direction}")
        if not isinstance(amount, int) or amount <= 0:
            raise LedgerError("ledger amounts are positive whole FCFA")
    debits = sum(a for _, d, a in lines if d == DEBIT)
    credits = sum(a for _, d, a in lines if d == CREDIT)
    if debits != credits:
        raise LedgerError(f"unbalanced transaction {tx_key}: debits {debits} != credits {credits}")
    if db.scalar(select(func.count()).select_from(LedgerEntry).where(LedgerEntry.tx_key == tx_key)):
        return False
    for account, direction, amount in lines:
        db.add(LedgerEntry(tx_key=tx_key, payment_id=payment_id, payout_id=payout_id, account=account,
                           direction=direction, amount=amount))
    db.flush()
    return True


def balances(db: Session) -> dict[str, int]:
    """Balance per account on its normal side: collection is debit-normal, every other account credit-normal."""
    totals = {a: {DEBIT: 0, CREDIT: 0} for a in ACCOUNTS}
    rows = db.execute(select(LedgerEntry.account, LedgerEntry.direction, func.sum(LedgerEntry.amount))
                      .group_by(LedgerEntry.account, LedgerEntry.direction)).all()
    for account, direction, total in rows:
        totals[account][direction] = int(total)
    return {a: (t[DEBIT] - t[CREDIT] if a == LedgerAccount.COLLECTION.value else t[CREDIT] - t[DEBIT])
            for a, t in totals.items()}


def unbalanced_transactions(db: Session) -> list[str]:
    """tx_keys whose debits and credits differ. Must always be empty."""
    rows = db.execute(select(LedgerEntry.tx_key, LedgerEntry.direction, func.sum(LedgerEntry.amount))
                      .group_by(LedgerEntry.tx_key, LedgerEntry.direction)).all()
    sums: dict[str, dict[str, int]] = {}
    for tx_key, direction, total in rows:
        sums.setdefault(tx_key, {DEBIT: 0, CREDIT: 0})[direction] = int(total)
    return sorted(k for k, v in sums.items() if v[DEBIT] != v[CREDIT])


def commission_split(payment: Payment) -> tuple[int, int]:
    """(commission, artisan share) for a customer payment under the configured commission model."""
    if get_settings().commission_model != "customer_split":
        return 0, payment.amount                      # the artisan already paid the commission separately
    commission = min(payment_service.compute_commission(payment.amount), payment.amount)
    return commission, payment.amount - commission


# ------------------------------------------------------------------------------- money events
def on_payment_succeeded(db: Session, payment: Payment) -> Payout | None:
    """Book a succeeded payment. For a customer payment this also creates the artisan's PENDING payout."""
    key = f"payment-succeeded:{payment.payment_id}"
    if payment.payment_type in FEE_TYPES:
        post(db, key, [("collection", DEBIT, payment.amount), ("platform_revenue", CREDIT, payment.amount)],
             payment_id=payment.payment_id)
        return None
    commission, share = commission_split(payment)
    lines: list[Line] = [("collection", DEBIT, payment.amount), ("artisan_pending", CREDIT, share)]
    if commission:
        lines.append(("platform_revenue", CREDIT, commission))
    post(db, key, lines, payment_id=payment.payment_id)
    existing = db.scalar(select(Payout).where(Payout.job_id == payment.job_id))
    if existing is not None:
        return existing
    payout = Payout(job_id=payment.job_id, artisan_id=payment.job.artisan_id, payment_id=payment.payment_id,
                    amount=share, commission=commission)
    db.add(payout)
    db.flush()
    return payout


def on_payout_paid(db: Session, payout: Payout) -> None:
    post(db, f"payout-paid:{payout.payout_id}",
         [("artisan_pending", DEBIT, payout.amount), ("artisan_paid", CREDIT, payout.amount)], payout_id=payout.payout_id)


def on_refund(db: Session, payment: Payment) -> None:
    """A refund is only REQUESTED here (no provider API call in the sandbox): the money is parked in refund_payable."""
    key = f"refund:{payment.payment_id}"
    if payment.payment_type in FEE_TYPES:
        post(db, key, [("platform_revenue", DEBIT, payment.amount), ("refund_payable", CREDIT, payment.amount)],
             payment_id=payment.payment_id)
        return
    payout = db.scalar(select(Payout).where(Payout.payment_id == payment.payment_id))
    commission = payout.commission if payout is not None else 0
    share = payment.amount - commission
    lines: list[Line] = [("artisan_pending", DEBIT, share), ("refund_payable", CREDIT, payment.amount)]
    if commission:
        lines.append(("platform_revenue", DEBIT, commission))
    post(db, key, lines, payment_id=payment.payment_id)
