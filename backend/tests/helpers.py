"""Readable scenario helpers shared by the tests (not tests themselves)."""
import itertools
import uuid
from dataclasses import dataclass

from app.models import Skill, User
from app.security.authentication import hash_password

PASSWORD = "Str0ng-pass!"
_phones = itertools.count(670000000)


@dataclass
class Actor:
    user_id: uuid.UUID
    phone: str
    role: str
    headers: dict
    artisan_id: str | None = None


class World:
    def __init__(self, client, session_factory):
        self.client = client
        self.factory = session_factory
        self._verifier: Actor | None = None
        self._admin: Actor | None = None

    # ---- users ---------------------------------------------------------------------------
    def login(self, phone: str) -> dict:
        res = self.client.post("/auth/login", json={"phone": phone, "password": PASSWORD})
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    def user(self, role: str = "CUSTOMER") -> Actor:
        phone = f"+237{next(_phones)}"
        if role in ("CUSTOMER", "ARTISAN"):
            res = self.client.post("/auth/register", json={"phone": phone, "password": PASSWORD, "role": role})
            assert res.status_code == 201, res.text
            user_id = uuid.UUID(res.json()["user_id"])
        else:  # staff accounts can only be created server-side, never through public registration
            with self.factory() as db:
                staff = User(phone=phone, password_hash=hash_password(PASSWORD), role=role)
                db.add(staff)
                db.commit()
                user_id = staff.user_id
        return Actor(user_id, phone, role, self.login(phone))

    def new_verifier(self) -> Actor:
        return self.user("VERIFIER")

    @property
    def verifier(self) -> Actor:
        self._verifier = self._verifier or self.user("VERIFIER")
        return self._verifier

    @property
    def admin(self) -> Actor:
        self._admin = self._admin or self.user("ADMIN")
        return self._admin

    # ---- catalogue -----------------------------------------------------------------------
    def skill(self, name: str = "Electrical Repair", safety_critical: bool = True) -> str:
        with self.factory() as db:
            skill = Skill(skill_name=f"{name}-{uuid.uuid4().hex[:6]}", safety_critical=safety_critical)
            db.add(skill)
            db.commit()
            return str(skill.skill_id)

    # ---- artisans --------------------------------------------------------------------------
    def artisan(self, skill_id: str, name: str = "Artisan", location: str = "Small Soppo, Buea",
                availability: str = "AVAILABLE", price: int | None = 8000, proficiency: str = "INTERMEDIATE",
                verified: bool = True) -> Actor:
        actor = self.user("ARTISAN")
        res = self.client.post("/artisans", headers=actor.headers, json={
            "full_name": name, "location": location, "availability_status": availability})
        assert res.status_code == 201, res.text
        actor.artisan_id = res.json()["artisan_id"]
        res = self.client.post(f"/artisans/{actor.artisan_id}/skills", headers=actor.headers, json={
            "skill_id": skill_id, "proficiency_level": proficiency, "typical_price": price})
        assert res.status_code == 201, res.text
        if verified:
            self.verify_skill(actor, skill_id)
        return actor

    def endorse(self, artisan: Actor, times: int = 2) -> None:
        for _ in range(times):
            endorser = self.user("CUSTOMER")
            res = self.client.post(f"/artisans/{artisan.artisan_id}/endorsements", headers=endorser.headers,
                                   json={"evidence_description": "He repaired my house wiring last year."})
            assert res.status_code == 201, res.text

    def verify_skill(self, artisan: Actor, skill_id: str, endorsements: int = 2) -> str:
        self.endorse(artisan, endorsements)
        res = self.client.post("/verifications", headers=artisan.headers, json={
            "check_type": "SKILL", "skill_id": skill_id, "evidence_description": "Ten years wiring houses in Buea."})
        assert res.status_code == 201, res.text
        check_id = res.json()["check_id"]
        for decision in ("UNDER_REVIEW", "APPROVED"):
            res = self.client.post(f"/verifications/{check_id}/decision", headers=self.verifier.headers,
                                   json={"decision": decision, "decision_notes": "SIMULATED test decision"})
            assert res.status_code == 200, res.text
        return check_id

    # ---- requests / jobs -------------------------------------------------------------------
    def request(self, customer: Actor, skill_id: str, location: str = "Small Soppo, Buea",
                budget: int | None = 10000, needs_inspection: bool = False) -> str:
        res = self.client.post("/service-requests", headers=customer.headers, json={
            "skill_id": skill_id, "description": "Fix the faulty wiring in the kitchen", "location": location,
            "budget": budget, "needs_inspection": needs_inspection})
        assert res.status_code == 201, res.text
        return res.json()["request_id"]

    def job(self, customer: Actor, artisan: Actor, request_id: str, price: int | None = 9000) -> str:
        res = self.client.post("/jobs", headers=customer.headers, json={
            "request_id": request_id, "artisan_id": artisan.artisan_id, "proposed_price": price})
        assert res.status_code == 201, res.text
        return res.json()["job_id"]

    # ---- payments (SIMULATED provider: "approving" stands in for the mobile-money prompt) ----------
    def approve(self, payment_id: str, payer: Actor) -> dict:
        res = self.client.post(f"/payments/{payment_id}/simulate-approval", headers=payer.headers)
        assert res.status_code == 200, res.text
        return res.json()

    def fee_due(self, job_id: str, artisan: Actor) -> dict:
        """Artisan agrees (and, for fixed-price jobs, confirms after probation) -> the fee payment to approve."""
        res = self.client.post(f"/jobs/{job_id}/accept", headers=artisan.headers)
        assert res.status_code == 200, res.text
        due = res.json()["payment_due"]
        if due is None:   # fixed price: the commission is created by the final confirmation
            res = self.client.post(f"/jobs/{job_id}/confirm-terms", headers=artisan.headers)
            assert res.status_code == 200, res.text
            due = res.json()["payment_due"]
        return due

    def accept(self, job_id: str, artisan: Actor) -> dict:
        """Artisan agrees, confirms and pays the platform fee -> job ACCEPTED."""
        self.approve(self.fee_due(job_id, artisan)["payment_id"], artisan)
        return self.client.get(f"/jobs/{job_id}", headers=artisan.headers).json()

    def fund(self, job_id: str, customer: Actor) -> dict:
        """Customer pays the agreed price into escrow."""
        res = self.client.post(f"/jobs/{job_id}/pay", headers=customer.headers)
        assert res.status_code == 201, res.text
        return self.approve(res.json()["payment_id"], customer)

    def work_started(self, customer: Actor, artisan: Actor, job_id: str) -> None:
        self.accept(job_id, artisan)
        self.fund(job_id, customer)
        res = self.client.post(f"/jobs/{job_id}/start", headers=artisan.headers)
        assert res.status_code == 200, res.text

    def complete(self, customer: Actor, artisan: Actor, job_id: str) -> None:
        for actor in (customer, artisan):
            res = self.client.post(f"/jobs/{job_id}/confirm-completion", headers=actor.headers)
            assert res.status_code == 200, res.text

    def job_in_progress(self, skill_id: str | None = None):
        skill_id = skill_id or self.skill()
        customer, artisan = self.user("CUSTOMER"), self.artisan(skill_id)
        job_id = self.job(customer, artisan, self.request(customer, skill_id))
        self.work_started(customer, artisan, job_id)
        return customer, artisan, job_id

    def completed_job(self, skill_id: str | None = None):
        customer, artisan, job_id = self.job_in_progress(skill_id)
        self.complete(customer, artisan, job_id)
        return customer, artisan, job_id
