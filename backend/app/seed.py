"""Demo seed data:  python -m app.seed

Creates staff accounts, the skill catalogue, and several COMPETING artisans so the matching engine
has more than one person to rank. John and Mary are NOT seeded - scripts/demo.py registers them live.

*** EVERYTHING HERE IS SIMULATED. No real person, ID check or skill assessment is involved. ***
Seed verification records say so in decision_notes. The default password is for local demos only.
"""
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import (
    ArtisanProfile, ArtisanSkill, CheckStatus, CheckType, Endorsement, Job, JobEvent, JobStatus, Review,
    RequestStatus, Role, ServiceRequest, Skill, TradeGroup, User, VerificationCheck,
)
from app.security.authentication import hash_password

DEMO_PASSWORD = os.environ.get("SEED_PASSWORD", "Demo-Pass-123!")
ADMIN_PHONE, VERIFIER_PHONE = "+237670000001", "+237670000002"
SIM_NOTE = "SIMULATED SEED DATA - no real identity or skill assessment was performed."

SKILLS = [
    ("Electrical Repair", "Wiring, sockets, breakers, fault finding", True),
    ("Plumbing", "Pipes, taps, water heaters, drainage", False),
    ("Carpentry", "Doors, roofs, furniture", False),
    ("Masonry", "Walls, floors, foundations", True),
    ("Mechanics", "Car and motorbike repair", False),
    ("Tailoring", "Clothes making and alterations", False),
    ("Hairdressing", "Braiding, cutting, styling", False),
]

# name, phone, location, skill, proficiency, price, availability, verified, ratings (completed-job history)
ARTISANS = [
    ("Paul Tabi", "+237690000011", "Molyko, Buea", "Electrical Repair", "EXPERT", 12000, "AVAILABLE", True, [5, 5, 4, 5, 4, 4, 5, 4]),
    ("Samuel Ngwa", "+237690000012", "Small Soppo, Buea", "Electrical Repair", "INTERMEDIATE", 7000, "AVAILABLE", False, []),
    ("Esther Mbah", "+237690000013", "Small Soppo, Buea", "Electrical Repair", "EXPERT", 9000, "UNAVAILABLE", True, [5, 5]),
    ("Ngu Peter", "+237690000014", "Down Beach, Limbe", "Electrical Repair", "EXPERT", 8000, "AVAILABLE", True, [4, 5, 5]),
    ("Grace Ndifor", "+237690000015", "Molyko, Buea", "Plumbing", "EXPERT", 6000, "AVAILABLE", True, [5, 4, 5]),
    ("Mama Rose", "+237690000016", "Great Soppo, Buea", "Tailoring", "EXPERT", 3000, "AVAILABLE", False, []),
]


def _user(db: Session, phone: str, role: str) -> User:
    user = db.scalar(select(User).where(User.phone == phone))
    if user is None:
        user = User(phone=phone, password_hash=hash_password(DEMO_PASSWORD), role=role)
        db.add(user)
        db.flush()
    return user


def seed(db: Session) -> None:
    if db.scalar(select(User).where(User.phone == ADMIN_PHONE)):
        print("Seed data already present - nothing to do.")
        return
    _user(db, ADMIN_PHONE, Role.ADMIN.value)
    verifier = _user(db, VERIFIER_PHONE, Role.VERIFIER.value)
    skills = {name: Skill(skill_name=name, description=desc, safety_critical=critical) for name, desc, critical in SKILLS}
    db.add_all(skills.values())
    db.flush()

    history_customer = _user(db, "+237690000030", Role.CUSTOMER.value)
    now = datetime.now(timezone.utc)

    for name, phone, location, skill_name, level, price, availability, verified, ratings in ARTISANS:
        owner = _user(db, phone, Role.ARTISAN.value)
        artisan = ArtisanProfile(user_id=owner.user_id, full_name=name, location=location,
                                 availability_status=availability, description="SIMULATED demo artisan",
                                 # Paul and Grace opted in to WhatsApp; the others did not (shows both cases).
                                 whatsapp_number=phone if name in ("Paul Tabi", "Grace Ndifor") else None)
        db.add(artisan)
        db.flush()
        skill = skills[skill_name]
        db.add(ArtisanSkill(
            artisan_id=artisan.artisan_id, skill_id=skill.skill_id, proficiency_level=level, typical_price=price,
            verification_status="VERIFIED" if verified else "UNVERIFIED"))
        if verified:
            # Individuals can vouch for only ONE artisan, so each verified artisan gets their own two endorsers.
            for n in range(2):
                endorser = _user(db, f"+2376910{ARTISANS.index((name, phone, location, skill_name, level, price, availability, verified, ratings)):02d}{n}00", Role.CUSTOMER.value)
                db.add(Endorsement(artisan_id=artisan.artisan_id, endorser_id=endorser.user_id,
                                   evidence_description="SIMULATED endorsement for demo data."))
            db.add(VerificationCheck(
                artisan_id=artisan.artisan_id, skill_id=skill.skill_id, verifier_id=verifier.user_id,
                check_type=CheckType.SKILL.value, status=CheckStatus.APPROVED.value,
                evidence_description="SIMULATED evidence", decision_notes=SIM_NOTE, reviewed_at=now))
        # A believable completed-work history: each rating belongs to a real (simulated) COMPLETED job.
        for i, rating in enumerate(ratings):
            req = ServiceRequest(customer_id=history_customer.user_id, skill_id=skill.skill_id,
                                 description="SIMULATED past job", location=location, budget=price,
                                 status=RequestStatus.COMPLETED.value)
            db.add(req)
            db.flush()
            done_at = now - timedelta(days=30 - i)
            job = Job(request_id=req.request_id, artisan_id=artisan.artisan_id, agreed_price=price,
                      proposed_price=price, proposed_by="CUSTOMER", artisan_agreed=True,
                      status=JobStatus.COMPLETED.value, customer_confirmed=True, artisan_confirmed=True,
                      completed_at=done_at)
            db.add(job)
            db.flush()
            db.add(JobEvent(job_id=job.job_id, actor_id=history_customer.user_id, event_type="JOB_COMPLETED",
                            event_metadata={"simulated_seed": True}))
            db.add(Review(job_id=job.job_id, reviewer_id=history_customer.user_id, rating=rating,
                          comment="SIMULATED review"))
    # An active, e-mail-verified trade group (SIMULATED). More groups are added by an admin via the API.
    admin = db.scalar(select(User).where(User.phone == ADMIN_PHONE))
    db.add(TradeGroup(name="Buea Electricians Association", email="contact@buea-electricians.example",
                      description="SIMULATED demo trade group", status="ACTIVE", created_by=admin.user_id,
                      email_verified_at=now))
    db.commit()
    print(f"Seeded. Admin {ADMIN_PHONE}, verifier {VERIFIER_PHONE}, password: {DEMO_PASSWORD}")


if __name__ == "__main__":
    with SessionLocal() as session:
        seed(session)
