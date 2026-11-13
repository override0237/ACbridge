"""Job chat ("connect flexibly"): the customer and artisan bargain in free text.

The CUSTOMER bargains; the ARTISAN states the final price. When the artisan writes a message that ENDS with an amount
and a currency (e.g. "final price: 9000 FCFA" or "9 000 XAF"), that amount becomes the job's proposed price
(proposed_by = ARTISAN) - the same field the rest of the platform already uses. The artisan's acceptance (POST /accept)
then agrees it, the price is frozen, the cooling-off period starts and the commission is computed from it. The customer
never fixes the price: an amount the customer types is just an offer in the conversation, and the customer's consent
is the payment (and the free withdrawal during the cooling-off period).

Rules (enforced here, never by the client):
  * Only the two parties can write; admins may read.
  * Only the ARTISAN can set the final price from the chat. An amount typed by the customer is just bargaining.
  * A price can be set only while the job is REQUESTED, fixed-price, and the artisan has not agreed yet.
  * The amount must be between MIN_PRICE and MAX_PRICE FCFA, written with the currency at the END of the message.
  * Phone numbers are hidden (so the deal stays on the platform where escrow, reviews and fees apply).
  * The chat closes for good once the customer's payment has succeeded (the app holds the money); the history stays readable.
  * Messages are append-only, 1-500 characters.
"""
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import BadRequestError, ConflictError, PermissionDeniedError
from app.models import Job, JobEvent, JobMessage, JobStatus, PricingMode
from app.services import job_service, payment_service

MAX_BODY = 500
MIN_PRICE = 500
MAX_PRICE = 5_000_000
CLOSED_STATUSES = (JobStatus.COMPLETED.value, JobStatus.CANCELLED.value)

# Amount at the very end of the text, currency last. Thousands may be separated by space, dot, comma or NBSP.
_AMOUNT_AT_END = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[ .,  ]\d{3})+|\d+)\s*(?:F\s?CFA|XAF|CFA)\s*[.!]*\s*$", re.IGNORECASE
)
_ENDS_WITH_NUMBER = re.compile(r"\d\s*[.!]*\s*$")
# Contiguous 9+ digit runs and international +CC numbers. Prices (max 7 digits) are never touched.
_PHONE = re.compile(r"\+\d{1,3}[ .-]?\d(?:[ .-]?\d){7,}|\d{9,}")
HIDDEN = "[number hidden]"


def parse_amount(text: str) -> int | None:
    """The amount at the end of `text` if it is followed by FCFA / F CFA / XAF / CFA, else None."""
    match = _AMOUNT_AT_END.search(text.strip())
    if not match:
        return None
    return int(re.sub(r"[ .,  ]", "", match.group(1)))


def ends_with_bare_number(text: str) -> bool:
    """True for 'ok 9000' (a number but no currency): the UI can remind the user to add the currency."""
    return parse_amount(text) is None and bool(_ENDS_WITH_NUMBER.search(text.strip()))


def mask_contacts(text: str) -> str:
    return _PHONE.sub(HIDDEN, text)


@dataclass
class SendResult:
    message: JobMessage
    price_status: str  # NONE | APPLIED | OUT_OF_RANGE | LOCKED | NOT_APPLICABLE | NOT_ARTISAN


def _price_status(job: Job, party: str, amount: int | None) -> str:
    if amount is None:
        return "NONE"
    if party != "ARTISAN":
        return "NOT_ARTISAN"          # the customer bargains; only the artisan states the final price
    if not (MIN_PRICE <= amount <= MAX_PRICE):
        return "OUT_OF_RANGE"
    if job.pricing_mode != PricingMode.FIXED_PRICE.value:
        return "NOT_APPLICABLE"
    if job.status != JobStatus.REQUESTED.value or job.artisan_agreed or job.agreed_price is not None:
        return "LOCKED"
    return "APPLIED"


def send_message(db: Session, user, job_id: uuid.UUID, body: str) -> SendResult:
    job = job_service._lock_job(db, job_id)
    party = job_service.party_of(job, user)
    if party is None:
        raise PermissionDeniedError("Only the customer and the artisan of this job can chat")
    if job.status in CLOSED_STATUSES:
        raise ConflictError(f"The chat is closed: this job is {job.status}")
    if job_service.job_is_paid(job):
        # The app now holds the customer's money: the deal is made and the bargaining is over.
        raise ConflictError("The chat is closed: the customer's payment has been received")
    text = body.strip()
    if not 1 <= len(text) <= MAX_BODY:
        raise BadRequestError(f"A message must be 1 to {MAX_BODY} characters")

    amount = parse_amount(text)                      # read from the ORIGINAL text, before masking
    status = _price_status(job, party, amount)
    message = JobMessage(job_id=job.job_id, sender_id=user.user_id, sender_role=party, body=mask_contacts(text))
    if status == "APPLIED":
        job.proposed_price, job.proposed_by = amount, "ARTISAN"
        message.proposed_price = amount
        db.add(message)
        db.flush()
        db.add(JobEvent(job_id=job.job_id, actor_id=user.user_id, event_type="PRICE_PROPOSED_IN_CHAT", event_metadata={
            "amount": amount, "message_id": str(message.message_id),
            "commission_if_agreed": payment_service.compute_commission(amount),
        }))
    else:
        db.add(message)
    db.commit()
    return SendResult(message, status)


def list_messages(db: Session, user, job_id: uuid.UUID) -> list[JobMessage]:
    job = job_service.get_job_for_party(db, user, job_id)   # parties and admins only
    return list(db.scalars(
        select(JobMessage).where(JobMessage.job_id == job.job_id).order_by(JobMessage.created_at, JobMessage.message_id)
    ))
