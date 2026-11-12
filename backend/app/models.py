"""SQLAlchemy 2.0 models for the ten ACbridge tables.

Integrity is enforced IN THE DATABASE (PK/FK/UNIQUE/CHECK/NOT NULL/triggers) and not only in Python.

Cardinality summary
  users 1 ──── 0..1 artisan_profiles      (UNIQUE user_id)
  artisan_profiles M ──── N skills        via artisan_skills (composite PK)
  artisan_profiles 1 ──── N endorsements  (UNIQUE artisan_id+endorser_id)
  artisan_profiles 1 ──── N verification_checks ; skills 1 ──── N verification_checks (SKILL type)
  users 1 ──── N service_requests ; skills 1 ──── N service_requests
  service_requests 1 ──── 0..1 jobs       (UNIQUE request_id: one artisan per request in the MVP)
  artisan_profiles 1 ──── N jobs ; jobs 1 ──── N job_events (append-only) ; jobs 1 ──── N reviews
  jobs 1 ──── N payments (commission / assignment fee / escrow; at most one non-failed per type)
  reviews: UNIQUE(job_id, reviewer_id)
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, DDL, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer,
    MetaData, SmallInteger, String, Text, UniqueConstraint, event, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid


# Same function the job_events trigger uses; every append-only table creates it (idempotent) so table order never matters.
_PG_BLOCK_FN = (
    "CREATE OR REPLACE FUNCTION acbridge_block_job_event_changes() RETURNS trigger AS $ "
    "BEGIN RAISE EXCEPTION 'append-only table'; END; $ LANGUAGE plpgsql"
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    ARTISAN = "ARTISAN"
    VERIFIER = "VERIFIER"
    ADMIN = "ADMIN"


class AvailabilityStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    BUSY = "BUSY"
    UNAVAILABLE = "UNAVAILABLE"


class ProficiencyLevel(str, enum.Enum):
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    EXPERT = "EXPERT"


class SkillVerificationStatus(str, enum.Enum):
    UNVERIFIED = "UNVERIFIED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class CheckType(str, enum.Enum):
    IDENTITY = "IDENTITY"
    SKILL = "SKILL"


class CheckStatus(str, enum.Enum):
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_MORE_EVIDENCE = "NEEDS_MORE_EVIDENCE"


class RequestStatus(str, enum.Enum):
    OPEN = "OPEN"
    MATCHED = "MATCHED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class JobStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    ACCEPTED = "ACCEPTED"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    DISPUTED = "DISPUTED"
    CANCELLED = "CANCELLED"


class HardshipKind(str, enum.Enum):
    DEATH = "DEATH"                                    # proof: death certificate
    ACCIDENT_OR_SERIOUS_ILLNESS = "ACCIDENT_OR_SERIOUS_ILLNESS"  # proof: medical records


class AffectedParty(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    ARTISAN = "ARTISAN"


class ClaimStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PricingMode(str, enum.Enum):
    FIXED_PRICE = "FIXED_PRICE"                # customer proposes an amount; artisan pays a % commission once they agree
    INSPECTION_REQUIRED = "INSPECTION_REQUIRED"  # price unknown until inspected; artisan pays a flat assignment fee


class PaymentType(str, enum.Enum):
    COMMISSION = "COMMISSION"          # artisan -> platform, % of the agreed price (fixed-price jobs)
    ASSIGNMENT_FEE = "ASSIGNMENT_FEE"  # artisan -> platform, flat fee (inspection jobs)
    JOB_PAYMENT = "JOB_PAYMENT"        # customer -> platform escrow, released to the artisan on completion


class PaymentStatus(str, enum.Enum):
    PENDING = "PENDING"      # waiting for the mobile-money approval
    SUCCEEDED = "SUCCEEDED"  # money received (for JOB_PAYMENT: held in escrow)
    FAILED = "FAILED"
    RELEASED = "RELEASED"    # escrow paid out to the artisan
    REFUNDED = "REFUNDED"    # escrow returned to the customer


def _in(column: str, enum_cls: type[enum.Enum]) -> str:
    return f"{column} IN ({', '.join(repr(m.value) for m in enum_cls)})"


class Base(DeclarativeBase):
    # Deterministic constraint names make future migrations predictable.
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False)


# --------------------------------------------------------------------------- A. users
class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", Role), name="role_valid"),)

    user_id: Mapped[uuid.UUID] = _uuid_pk()
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = _created_at()

    artisan_profile: Mapped["ArtisanProfile | None"] = relationship(back_populates="user", uselist=False)


# --------------------------------------------------------------------------- B. artisan_profiles
class ArtisanProfile(Base):
    __tablename__ = "artisan_profiles"
    __table_args__ = (
        CheckConstraint(_in("availability_status", AvailabilityStatus), name="availability_valid"),
        Index("ix_artisan_profiles_location", "location"),
        Index("ix_artisan_profiles_availability_status", "availability_status"),
    )

    artisan_id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str] = mapped_column(String(160), nullable=False)  # "Neighbourhood, Town"
    description: Mapped[str | None] = mapped_column(Text)
    # Opt-in: the artisan chooses to publish a WhatsApp number to matched customers (NULL = no WhatsApp contact).
    whatsapp_number: Mapped[str | None] = mapped_column(String(20))
    availability_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AvailabilityStatus.AVAILABLE.value,
        server_default=AvailabilityStatus.AVAILABLE.value,
    )
    # Not in the original spec: lets admins suspend an artisan (matching rule "suspended => ineligible").
    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = _created_at()

    user: Mapped[User] = relationship(back_populates="artisan_profile")
    skills: Mapped[list["ArtisanSkill"]] = relationship(back_populates="artisan", cascade="all, delete-orphan")
    endorsements: Mapped[list["Endorsement"]] = relationship(back_populates="artisan")
    verification_checks: Mapped[list["VerificationCheck"]] = relationship(back_populates="artisan")
    jobs: Mapped[list["Job"]] = relationship(back_populates="artisan")


# --------------------------------------------------------------------------- C. skills
class Skill(Base):
    __tablename__ = "skills"

    skill_id: Mapped[uuid.UUID] = _uuid_pk()
    skill_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Not in the original spec: safety-critical skills (e.g. electrical work) REQUIRE verification to be matched.
    safety_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


# --------------------------------------------------------------------------- D. artisan_skills
class ArtisanSkill(Base):
    __tablename__ = "artisan_skills"
    __table_args__ = (
        CheckConstraint(_in("proficiency_level", ProficiencyLevel), name="proficiency_valid"),
        CheckConstraint(_in("verification_status", SkillVerificationStatus), name="verification_valid"),
        CheckConstraint("typical_price IS NULL OR typical_price >= 0", name="price_non_negative"),
        # Matching starts from "who has skill X and is it verified?"
        Index("ix_artisan_skills_skill_id_verification_status", "skill_id", "verification_status"),
    )

    artisan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artisan_profiles.artisan_id"), primary_key=True)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.skill_id"), primary_key=True)
    proficiency_level: Mapped[str] = mapped_column(String(16), nullable=False)
    verification_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=SkillVerificationStatus.UNVERIFIED.value,
        server_default=SkillVerificationStatus.UNVERIFIED.value,
    )
    # Not in the original spec: the artisan's typical price (FCFA) for this skill, used for price compatibility.
    typical_price: Mapped[int | None] = mapped_column(Integer)

    artisan: Mapped[ArtisanProfile] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship()


# --------------------------------------------------------------------------- E. endorsements
class Endorsement(Base):
    __tablename__ = "endorsements"
    __table_args__ = (
        UniqueConstraint("artisan_id", "endorser_id", name="uq_endorsements_artisan_endorser"),
        Index("ix_endorsements_artisan_id", "artisan_id"),
    )

    endorsement_id: Mapped[uuid.UUID] = _uuid_pk()
    artisan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artisan_profiles.artisan_id"), nullable=False)
    endorser_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    evidence_description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    artisan: Mapped[ArtisanProfile] = relationship(back_populates="endorsements")
    endorser: Mapped[User] = relationship()


# --------------------------------------------------------------------------- F. verification_checks
class VerificationCheck(Base):
    __tablename__ = "verification_checks"
    __table_args__ = (
        CheckConstraint(_in("check_type", CheckType), name="type_valid"),
        CheckConstraint(_in("status", CheckStatus), name="status_valid"),
        CheckConstraint("check_type = 'IDENTITY' OR skill_id IS NOT NULL", name="skill_check_needs_skill"),
        Index("ix_verification_checks_status", "status"),
        Index("ix_verification_checks_artisan_id_check_type", "artisan_id", "check_type"),
    )

    check_id: Mapped[uuid.UUID] = _uuid_pk()
    artisan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artisan_profiles.artisan_id"), nullable=False)
    # Not in the original spec: the skill being verified (NULL for IDENTITY checks).
    skill_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("skills.skill_id"))
    # Nullable: unknown until a verifier claims the check.
    verifier_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.user_id"))
    check_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=CheckStatus.PENDING.value, server_default=CheckStatus.PENDING.value
    )
    evidence_description: Mapped[str] = mapped_column(Text, nullable=False)
    # Not in the original spec: private uploaded evidence (never exposed via public endpoints).
    evidence_file_path: Mapped[str | None] = mapped_column(String(255))
    decision_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    artisan: Mapped[ArtisanProfile] = relationship(back_populates="verification_checks")
    skill: Mapped[Skill | None] = relationship()
    verifier: Mapped[User | None] = relationship()


# --------------------------------------------------------------------------- G. service_requests
class ServiceRequest(Base):
    __tablename__ = "service_requests"
    __table_args__ = (
        CheckConstraint(_in("status", RequestStatus), name="status_valid"),
        CheckConstraint("budget IS NULL OR budget >= 0", name="budget_non_negative"),
        Index("ix_service_requests_status", "status"),
        Index("ix_service_requests_skill_id", "skill_id"),
        Index("ix_service_requests_customer_id", "customer_id"),
        Index("ix_service_requests_location", "location"),
    )

    request_id: Mapped[uuid.UUID] = _uuid_pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    skill_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("skills.skill_id"), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(String(160), nullable=False)
    budget: Mapped[int | None] = mapped_column(Integer)  # FCFA has no minor unit, so integers are exact
    # True when the problem must be examined before a price can be given (-> INSPECTION_REQUIRED job).
    needs_inspection: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=RequestStatus.OPEN.value, server_default=RequestStatus.OPEN.value
    )
    created_at: Mapped[datetime] = _created_at()

    customer: Mapped[User] = relationship()
    skill: Mapped[Skill] = relationship()
    job: Mapped["Job | None"] = relationship(back_populates="request", uselist=False)


# --------------------------------------------------------------------------- H. jobs
class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(_in("status", JobStatus), name="status_valid"),
        CheckConstraint(_in("pricing_mode", PricingMode), name="pricing_mode_valid"),
        CheckConstraint("agreed_price IS NULL OR agreed_price >= 0", name="price_non_negative"),
        CheckConstraint("proposed_price IS NULL OR proposed_price >= 0", name="proposed_price_non_negative"),
        # Work cannot start (or finish) without an agreed price - guaranteed by the database itself.
        CheckConstraint(
            "status NOT IN ('IN_PROGRESS', 'PENDING_CONFIRMATION', 'COMPLETED') OR agreed_price IS NOT NULL",
            name="started_needs_agreed_price",
        ),
        # A job can only be COMPLETED if BOTH parties confirmed - enforced by the database itself.
        CheckConstraint(
            "status <> 'COMPLETED' OR (customer_confirmed = true AND artisan_confirmed = true "
            "AND completed_at IS NOT NULL)",
            name="completed_needs_both_confirmations",
        ),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_artisan_id", "artisan_id"),
    )

    job_id: Mapped[uuid.UUID] = _uuid_pk()
    request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("service_requests.request_id"), unique=True, nullable=False)
    artisan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artisan_profiles.artisan_id"), nullable=False)
    pricing_mode: Mapped[str] = mapped_column(
        String(24), nullable=False, default=PricingMode.FIXED_PRICE.value, server_default=PricingMode.FIXED_PRICE.value
    )
    proposed_price: Mapped[int | None] = mapped_column(Integer)   # latest offer on the table (FCFA)
    proposed_by: Mapped[str | None] = mapped_column(String(8))    # 'CUSTOMER' or 'ARTISAN'
    agreed_price: Mapped[int | None] = mapped_column(Integer)     # NULL until both sides accept an amount
    terms_agreed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # End of the cooling-off period that starts when the price is agreed (see job_service).
    probation_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    artisan_agreed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default=JobStatus.REQUESTED.value, server_default=JobStatus.REQUESTED.value
    )
    customer_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    artisan_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = _created_at()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    request: Mapped[ServiceRequest] = relationship(back_populates="job")
    artisan: Mapped[ArtisanProfile] = relationship(back_populates="jobs")
    events: Mapped[list["JobEvent"]] = relationship(back_populates="job", order_by="JobEvent.created_at")
    reviews: Mapped[list["Review"]] = relationship(back_populates="job")
    payments: Mapped[list["Payment"]] = relationship(back_populates="job", order_by="Payment.created_at")
    hardship_claims: Mapped[list["HardshipClaim"]] = relationship(back_populates="job")


# --------------------------------------------------------------------------- K. payments (platform money flow)
class Payment(Base):
    """Every money movement goes through the platform and is recorded here.

    COMMISSION / ASSIGNMENT_FEE : artisan pays the platform.
    JOB_PAYMENT                 : customer pays into escrow; RELEASED to the artisan on completion or
                                  REFUNDED if the job is cancelled.
    NOTE: the payment provider is SIMULATED in this MVP - no real money moves.
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(_in("payment_type", PaymentType), name="type_valid"),
        CheckConstraint(_in("status", PaymentStatus), name="status_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        # At most one non-failed payment of each type per job: no double commission, no double escrow.
        Index(
            "uq_payments_one_active_per_type", "job_id", "payment_type", unique=True,
            postgresql_where=text("status <> 'FAILED'"), sqlite_where=text("status <> 'FAILED'"),
        ),
        Index("ix_payments_status", "status"),
        Index("ix_payments_payer_id", "payer_id"),
    )

    payment_id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.job_id"), nullable=False)
    payer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    payment_type: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # FCFA (XAF)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="XAF", server_default="XAF")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=PaymentStatus.PENDING.value, server_default=PaymentStatus.PENDING.value
    )
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(String(200))
    # Client-supplied Idempotency-Key: the same key from the same payer always returns the same payment.
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = _created_at()
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped[Job] = relationship(back_populates="payments")
    payer: Mapped[User] = relationship()


Index(
    "uq_payments_idempotency", Payment.payer_id, Payment.idempotency_key, unique=True,
    postgresql_where=text("idempotency_key IS NOT NULL"), sqlite_where=text("idempotency_key IS NOT NULL"),
)


# --------------------------------------------------------------------------- K2. ledger, payouts, webhooks, audit
class LedgerAccount(str, enum.Enum):
    COLLECTION = "collection"                  # money held in ACbridge's collection account at the provider
    PLATFORM_REVENUE = "platform_revenue"      # commission earned by ACbridge
    ARTISAN_PENDING = "artisan_pending"        # owed to artisans, waiting for job completion
    ARTISAN_PAID = "artisan_paid"              # cumulative amounts disbursed to artisans
    REFUND_PAYABLE = "refund_payable"          # owed back to customers (a refund REQUEST is recorded only)


class PayoutStatus(str, enum.Enum):
    PENDING = "PENDING"      # created when the customer's payment succeeds
    RELEASED = "RELEASED"    # job completed and no open dispute: the disbursement is authorised
    HELD = "HELD"            # stopped by a dispute or by an operator
    PAID = "PAID"            # the provider confirmed the disbursement
    FAILED = "FAILED"        # voided (the escrow was refunded) or the disbursement failed


class LedgerEntry(Base):
    """One line of a double-entry transaction. Every tx_key balances: total DEBIT = total CREDIT.
    Append-only (the database refuses UPDATE and DELETE). Amounts are whole FCFA."""

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint(_in("account", LedgerAccount), name="account_valid"),
        CheckConstraint("direction IN ('DEBIT', 'CREDIT')", name="direction_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        # Replaying the same event can never post the same line twice.
        UniqueConstraint("tx_key", "account", "direction", name="uq_ledger_tx_line"),
        Index("ix_ledger_entries_payment_id", "payment_id"),
    )

    entry_id: Mapped[uuid.UUID] = _uuid_pk()
    tx_key: Mapped[str] = mapped_column(String(100), nullable=False)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payments.payment_id"))
    payout_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("payouts.payout_id"))
    account: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(6), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class Payout(Base):
    """The artisan's share of a paid job. One per job."""

    __tablename__ = "payouts"
    __table_args__ = (
        CheckConstraint(_in("status", PayoutStatus), name="status_valid"),
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("commission >= 0", name="commission_non_negative"),
        UniqueConstraint("job_id", name="uq_payouts_job_id"),
        Index("ix_payouts_status", "status"),
    )

    payout_id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.job_id"), nullable=False)
    artisan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artisan_profiles.artisan_id"), nullable=False)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("payments.payment_id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)       # what the artisan receives
    commission: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")  # cut from the payment
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=PayoutStatus.PENDING.value, server_default=PayoutStatus.PENDING.value
    )
    provider_reference: Mapped[str | None] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(String(300))               # last hold/release reason
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow,
                                                 server_default=func.now(), nullable=False)

    job: Mapped[Job] = relationship()
    artisan: Mapped[ArtisanProfile] = relationship()
    payment: Mapped[Payment] = relationship()


class WebhookEvent(Base):
    """Every provider callback we accepted, by the provider's event id: a replay is recognised and ignored."""

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)

    webhook_id: Mapped[uuid.UUID] = _uuid_pk()
    provider: Mapped[str] = mapped_column(String(24), nullable=False)
    event_id: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = _created_at()


class AuditLog(Base):
    """Append-only trail of money events and operator actions. Stores a HASH of the payload, never the raw payload."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_target", "target"),)

    audit_id: Mapped[uuid.UUID] = _uuid_pk()
    actor_type: Mapped[str] = mapped_column(String(12), nullable=False)    # USER, OPERATOR, PROVIDER or SYSTEM
    actor_id: Mapped[str | None] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    target: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = _created_at()


for _table in (LedgerEntry.__table__, AuditLog.__table__):   # money history is tamper-proof, like job_events
    event.listen(_table, "after_create", DDL(_PG_BLOCK_FN).execute_if(dialect="postgresql"))
    for _op in ("UPDATE", "DELETE"):
        event.listen(
            _table, "after_create",
            DDL(f"CREATE TRIGGER trg_{_table.name}_no_{_op.lower()} BEFORE {_op} ON {_table.name} "
                f"BEGIN SELECT RAISE(ABORT, '{_table.name} is append-only'); END").execute_if(dialect="sqlite"),
        )
        event.listen(
            _table, "after_create",
            DDL(f"CREATE TRIGGER trg_{_table.name}_no_{_op.lower()} BEFORE {_op} ON {_table.name} "
                f"FOR EACH ROW EXECUTE FUNCTION acbridge_block_job_event_changes()").execute_if(dialect="postgresql"),
        )


# --------------------------------------------------------------------------- L. hardship_claims
class HardshipClaim(Base):
    """The ONLY route to refund platform fees: proven death or serious accident/illness of a party.

    A party files the claim and uploads a death certificate / medical record; an administrator checks the
    document and decides. Approval cancels the job and refunds the fee AND the escrow.
    """

    __tablename__ = "hardship_claims"
    __table_args__ = (
        CheckConstraint(_in("kind", HardshipKind), name="kind_valid"),
        CheckConstraint(_in("affected_party", AffectedParty), name="party_valid"),
        CheckConstraint(_in("status", ClaimStatus), name="status_valid"),
        # An approved claim must have been backed by a stored document.
        CheckConstraint("status <> 'APPROVED' OR document_path IS NOT NULL", name="approved_needs_document"),
        Index("uq_hardship_one_open_claim_per_job", "job_id", unique=True,
              postgresql_where=text("status = 'PENDING'"), sqlite_where=text("status = 'PENDING'")),
        Index("ix_hardship_claims_status", "status"),
    )

    claim_id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.job_id"), nullable=False)
    claimant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    affected_party: Mapped[str] = mapped_column(String(16), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    document_path: Mapped[str | None] = mapped_column(String(255))   # private; never exposed through the API
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ClaimStatus.PENDING.value, server_default=ClaimStatus.PENDING.value
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.user_id"))
    decision_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped[Job] = relationship(back_populates="hardship_claims")
    claimant: Mapped[User] = relationship(foreign_keys=[claimant_id])


# --------------------------------------------------------------------------- I. job_events (append-only)
class JobEvent(Base):
    __tablename__ = "job_events"
    __table_args__ = (Index("ix_job_events_job_id_created_at", "job_id", "created_at"),)

    event_id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.job_id"), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    event_metadata: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    created_at: Mapped[datetime] = _created_at()

    job: Mapped[Job] = relationship(back_populates="events")
    actor: Mapped[User] = relationship()


# Audit history must be tamper-proof, so the DATABASE rejects UPDATE/DELETE on job_events
# (an application bug or a compromised API route still cannot rewrite history).
_pg_fn = DDL(
    "CREATE OR REPLACE FUNCTION acbridge_block_job_event_changes() RETURNS trigger AS $$ "
    "BEGIN RAISE EXCEPTION 'job_events is append-only'; END; $$ LANGUAGE plpgsql"
)
_pg_trigger = DDL(
    "CREATE TRIGGER trg_job_events_immutable BEFORE UPDATE OR DELETE ON job_events "
    "FOR EACH ROW EXECUTE FUNCTION acbridge_block_job_event_changes()"
)
event.listen(JobEvent.__table__, "after_create", _pg_fn.execute_if(dialect="postgresql"))
event.listen(JobEvent.__table__, "after_create", _pg_trigger.execute_if(dialect="postgresql"))
for _op in ("UPDATE", "DELETE"):
    event.listen(
        JobEvent.__table__,
        "after_create",
        DDL(
            f"CREATE TRIGGER trg_job_events_no_{_op.lower()} BEFORE {_op} ON job_events "
            "BEGIN SELECT RAISE(ABORT, 'job_events is append-only'); END"
        ).execute_if(dialect="sqlite"),
    )


# --------------------------------------------------------------------------- I2. job chat
class JobMessage(Base):
    """One chat message between the two parties of a job. Append-only. proposed_price is set when the customer's
    message (ending in an amount and a currency) became the job's proposed price."""

    __tablename__ = "job_messages"
    __table_args__ = (
        CheckConstraint("length(body) BETWEEN 1 AND 500", name="body_length"),
        CheckConstraint("sender_role IN ('CUSTOMER', 'ARTISAN')", name="sender_role_valid"),
        CheckConstraint("proposed_price IS NULL OR proposed_price > 0", name="proposed_price_positive"),
        Index("ix_job_messages_job_id_created_at", "job_id", "created_at"),
    )

    message_id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.job_id"), nullable=False)
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    sender_role: Mapped[str] = mapped_column(String(8), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_price: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()


event.listen(JobMessage.__table__, "after_create", DDL(_PG_BLOCK_FN).execute_if(dialect="postgresql"))
for _op in ("UPDATE", "DELETE"):  # chat history is evidence in a dispute: the DATABASE refuses edits and deletes
    event.listen(
        JobMessage.__table__,
        "after_create",
        DDL(
            f"CREATE TRIGGER trg_job_messages_no_{_op.lower()} BEFORE {_op} ON job_messages "
            "BEGIN SELECT RAISE(ABORT, 'job_messages is append-only'); END"
        ).execute_if(dialect="sqlite"),
    )
    event.listen(
        JobMessage.__table__,
        "after_create",
        DDL(
            f"CREATE TRIGGER trg_job_messages_no_{_op.lower()} BEFORE {_op} ON job_messages "
            "FOR EACH ROW EXECUTE FUNCTION acbridge_block_job_event_changes()"
        ).execute_if(dialect="postgresql"),
    )


# --------------------------------------------------------------------------- J. reviews
class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        UniqueConstraint("job_id", "reviewer_id", name="uq_reviews_job_reviewer"),
    )

    review_id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.job_id"), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()

    job: Mapped[Job] = relationship(back_populates="reviews")
    reviewer: Mapped[User] = relationship()
