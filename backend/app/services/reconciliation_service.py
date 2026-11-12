"""Reconciliation: do the numbers the PROVIDER reports agree with ACbridge's ledger?

In the sandbox the "provider side" is derived from the provider-facing records (payments the provider captured, refunds
requested, payouts it confirmed). A real provider would give a settlement report here. For demos, an operator may pass
`provider_collected_override` to simulate a provider total that disagrees and see the Mismatch warning.

Also flags artisans whose COMPLETED jobs have no matching successful customer payment (possible off-platform payment).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ArtisanProfile, Job, JobStatus, Payment, PaymentStatus, PaymentType, Payout, PayoutStatus
from app.services import ledger_service

CAPTURED = (PaymentStatus.SUCCEEDED.value, PaymentStatus.RELEASED.value, PaymentStatus.REFUNDED.value)


def reconcile(db: Session, provider_collected_override: int | None = None) -> dict:
    payments = list(db.scalars(select(Payment)))
    provider_collected = sum(p.amount for p in payments if p.status in CAPTURED)
    provider_refunds = sum(p.amount for p in payments if p.status == PaymentStatus.REFUNDED.value)
    provider_disbursed = sum(po.amount for po in db.scalars(select(Payout)) if po.status == PayoutStatus.PAID.value)
    if provider_collected_override is not None:
        provider_collected = provider_collected_override

    ledger = ledger_service.balances(db)
    unbalanced = ledger_service.unbalanced_transactions(db)
    differences = {
        "collected": provider_collected - ledger["collection"],
        "disbursed": provider_disbursed - ledger["artisan_paid"],
        "refunds": provider_refunds - ledger["refund_payable"],
    }

    # Completed jobs that were never paid through the platform, grouped by artisan.
    unpaid: dict[str, dict] = {}
    for job in db.scalars(select(Job).where(Job.status == JobStatus.COMPLETED.value)):
        paid = any(p.payment_type == PaymentType.JOB_PAYMENT.value and p.status in CAPTURED[:2] for p in job.payments)
        if not paid:
            artisan = db.get(ArtisanProfile, job.artisan_id)
            entry = unpaid.setdefault(str(job.artisan_id), {"artisan_id": str(job.artisan_id),
                                                           "artisan_name": artisan.full_name if artisan else "?",
                                                           "jobs": 0})
            entry["jobs"] += 1

    mismatch = any(v != 0 for v in differences.values()) or bool(unbalanced)
    return {
        "ledger": ledger,
        "provider": {"collected": provider_collected, "refunds": provider_refunds, "disbursed": provider_disbursed,
                     "simulated": True},
        "differences": differences,
        "unbalanced_transactions": unbalanced,
        "mismatch": mismatch,
        "status": "MISMATCH" if mismatch else "OK",
        "completed_jobs_without_payment": list(unpaid.values()),
    }
