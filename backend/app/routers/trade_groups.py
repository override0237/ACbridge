"""Trade-group vouching endpoints and the e-mail confirmation pages.

Artisan (logged in)  : list groups, request a vouch, see status, resend.
Trade group (NO login): receives an e-mail, opens the link, reviews the artisan and confirms or declines.
Admin                : registers groups, revokes vouches (see routers/admin.py).
"""
import html
import uuid

from fastapi import APIRouter, Depends, Form, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.errors import DomainError, NotFoundError
from app.models import Role, TradeGroupVouch, User, VouchStatus
from app.schemas import (
    PublicVouchOut, TokenIn, TradeGroupPublicOut, VouchDetailsOut, VouchOut, VouchRequestIn, VouchRespondIn,
)
from app.security.authentication import get_current_user
from app.security.permissions import require_roles
from app.security.rate_limit import rate_limit
from app.services import trade_group_service as svc
from app.services.verification_service import get_artisan_or_404

router = APIRouter(tags=["trade-group vouches"])
token_limit = Depends(rate_limit("vouch-token", 30, 600))   # throttles anyone probing the public link endpoints


def vouch_out(vouch: TradeGroupVouch, email_sent: bool | None = None, message: str = "") -> VouchOut:
    settings = get_settings()
    return VouchOut(
        vouch_id=vouch.vouch_id, group_id=vouch.group_id, group_name=vouch.group.name, artisan_id=vouch.artisan_id,
        skill_id=vouch.skill_id, skill_name=vouch.skill.skill_name, status=vouch.status,
        artisan_note=vouch.artisan_note, created_at=vouch.created_at, decided_at=vouch.decided_at,
        token_expires_at=vouch.token_expires_at,
        email_status=None if email_sent is None else ("SENT" if email_sent else "FAILED"),
        simulated_email=settings.email_mode == "console",
        message=message or {
            "PENDING_CONFIRMATION": f"Waiting for {vouch.group.name} to confirm by e-mail.",
            "CONFIRMED": f"{vouch.group.name} vouched for you. This skill is now verified.",
            "REJECTED": f"{vouch.group.name} declined this request.",
            "EXPIRED": "The link expired. You can send the request again.",
            "REVOKED": "This vouch was withdrawn by an administrator.",
        }[vouch.status],
    )


# ----------------------------------------------------------------------------- artisan side
@router.get("/trade-groups", response_model=list[TradeGroupPublicOut])
def list_trade_groups(db: Session = Depends(get_db)):
    """Active, e-mail-verified groups an artisan can ask. E-mail addresses are never exposed."""
    return svc.list_active_groups(db)


@router.post("/artisans/{artisan_id}/trade-group-vouches", response_model=VouchOut,
             status_code=status.HTTP_201_CREATED, dependencies=[Depends(rate_limit("vouch-request", 5, 3600))])
def request_vouch(artisan_id: uuid.UUID, payload: VouchRequestIn, user: User = Depends(require_roles(Role.ARTISAN)),
                  db: Session = Depends(get_db)) -> VouchOut:
    """The 'Vouch from Trade-group' checkbox: e-mails the group a single-use confirmation link."""
    vouch, sent = svc.request_vouch(db, user, artisan_id, payload.group_id, payload.skill_id, payload.note)
    return vouch_out(vouch, sent, "Request sent. The trade group has been e-mailed." if sent
                     else "Request saved but the e-mail could not be sent. Use resend to try again.")


@router.get("/artisans/{artisan_id}/trade-group-vouches", response_model=list[VouchOut])
def my_vouches(artisan_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    artisan = get_artisan_or_404(db, artisan_id)
    if artisan.user_id != user.user_id and user.role not in (Role.ADMIN.value, Role.VERIFIER.value):
        raise NotFoundError("Artisan not found")   # other people's requests stay private
    return [vouch_out(v) for v in svc.list_for_artisan(db, artisan_id)]


@router.post("/artisans/{artisan_id}/trade-group-vouches/{vouch_id}/resend", response_model=VouchOut,
             dependencies=[Depends(rate_limit("vouch-request", 5, 3600))])
def resend(artisan_id: uuid.UUID, vouch_id: uuid.UUID, user: User = Depends(require_roles(Role.ARTISAN)),
           db: Session = Depends(get_db)) -> VouchOut:
    vouch, sent = svc.resend_vouch(db, user, artisan_id, vouch_id)
    return vouch_out(vouch, sent)


# ----------------------------------------------------------------------------- trade group side (token = proof of access)
@router.get("/trade-group-vouches/details", response_model=VouchDetailsOut, dependencies=[token_limit])
def vouch_details(token: str = Query(min_length=20, max_length=200), db: Session = Depends(get_db)) -> VouchDetailsOut:
    return _details(svc.get_by_token(db, token))


def _details(vouch: TradeGroupVouch) -> VouchDetailsOut:
    return VouchDetailsOut(
        group_name=vouch.group.name, artisan_name=vouch.artisan.full_name, artisan_location=vouch.artisan.location,
        skill_name=vouch.skill.skill_name, artisan_note=vouch.artisan_note, status=vouch.status,
        expires_at=vouch.token_expires_at)


@router.post("/trade-group-vouches/respond", response_model=VouchDetailsOut, dependencies=[token_limit])
def respond(payload: VouchRespondIn, db: Session = Depends(get_db)) -> VouchDetailsOut:
    """The trade group's decision. Single use: the link stops working once it has been answered."""
    return _details(svc.respond(db, payload.token, payload.decision == "CONFIRM"))


@router.post("/trade-groups/verify-email", response_model=TradeGroupPublicOut, dependencies=[token_limit])
def verify_group_email(payload: TokenIn, db: Session = Depends(get_db)):
    return svc.verify_group_email(db, payload.token)


# ----------------------------------------------------------------------------- ready-made pages (no frontend needed)
_STYLE = ("body{font-family:system-ui,sans-serif;max-width:34rem;margin:2rem auto;padding:0 1rem;color:#1c2430}"
          "h1{font-size:1.4rem}.card{border:1px solid #d5dbe5;border-radius:10px;padding:1rem 1.25rem}"
          "button{font-size:1rem;padding:.7rem 1.2rem;border:0;border-radius:8px;cursor:pointer;margin-right:.5rem}"
          ".yes{background:#1a7f45;color:#fff}.no{background:#eee}.note{color:#566}")
_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY", "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


def _page(title: str, body: str, code: int = 200) -> HTMLResponse:
    doc = (f"<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
           f"initial-scale=1'><title>{html.escape(title)}</title><style>{_STYLE}</style><body><h1>ACbridge</h1>"
           f"<div class='card'>{body}</div></body></html>")
    return HTMLResponse(doc, status_code=code, headers=_HEADERS)


def _error_page(exc: DomainError) -> HTMLResponse:
    return _page("Link problem", f"<p>{html.escape(exc.detail)}</p>", exc.status_code)


@router.get("/trade-group-vouches/confirm-page", response_class=HTMLResponse, include_in_schema=False,
            dependencies=[token_limit])
def confirm_page(token: str = Query(min_length=20, max_length=200), db: Session = Depends(get_db)):
    try:
        d = _details(svc.get_by_token(db, token))
    except DomainError as exc:
        return _error_page(exc)
    note = f"<p class='note'>Message from the artisan: {html.escape(d.artisan_note)}</p>" if d.artisan_note else ""
    simulated = ("<p class='note'>SIMULATED e-mail mode: this is a demo, nothing was really e-mailed.</p>"
                 if get_settings().email_mode == "console" else "")
    return _page("Vouch request", (
        f"<p><b>{html.escape(d.artisan_name)}</b> ({html.escape(d.artisan_location)}) asks "
        f"<b>{html.escape(d.group_name)}</b> to vouch for their <b>{html.escape(d.skill_name)}</b> skills.</p>{note}"
        "<p>Vouch only if you personally know their work. Customers will rely on it.</p>"
        "<form method='post' action='/trade-group-vouches/confirm-page'>"
        f"<input type='hidden' name='token' value='{html.escape(token)}'>"
        "<button class='yes' name='decision' value='CONFIRM'>Yes, I vouch for this person</button>"
        f"<button class='no' name='decision' value='REJECT'>No / I do not know them</button></form>{simulated}"))


@router.post("/trade-group-vouches/confirm-page", response_class=HTMLResponse, include_in_schema=False,
             dependencies=[token_limit])
def confirm_page_submit(token: str = Form(min_length=20, max_length=200), decision: str = Form(),
                        db: Session = Depends(get_db)):
    if decision not in ("CONFIRM", "REJECT"):
        return _page("Invalid", "<p>Invalid choice.</p>", 400)
    try:
        vouch = svc.respond(db, token, decision == "CONFIRM")
    except DomainError as exc:
        return _error_page(exc)
    if vouch.status == VouchStatus.CONFIRMED.value:
        return _page("Thank you", f"<p>Thank you. You vouched for <b>{html.escape(vouch.artisan.full_name)}</b>. "
                                  "Their skill is now marked as verified on ACbridge.</p>")
    return _page("Thank you", "<p>Thank you. Your answer was recorded: no vouch was given.</p>")


@router.get("/trade-groups/verify-page", response_class=HTMLResponse, include_in_schema=False, dependencies=[token_limit])
def verify_page(token: str = Query(min_length=20, max_length=200), db: Session = Depends(get_db)):
    group = svc.group_for_verification_token(db, token)
    if group is None:
        return _page("Link problem", "<p>This link is invalid or has already been used.</p>", 404)
    return _page("Confirm trade group", (
        f"<p>Confirm that this e-mail address belongs to <b>{html.escape(group.name)}</b> and that you agree to be "
        "asked to vouch for artisans through ACbridge. Nothing is confirmed without your approval each time.</p>"
        "<form method='post' action='/trade-groups/verify-page'>"
        f"<input type='hidden' name='token' value='{html.escape(token)}'>"
        "<button class='yes'>Yes, confirm this address</button></form>"))


@router.post("/trade-groups/verify-page", response_class=HTMLResponse, include_in_schema=False, dependencies=[token_limit])
def verify_page_submit(token: str = Form(min_length=20, max_length=200), db: Session = Depends(get_db)):
    try:
        group = svc.verify_group_email(db, token)
    except DomainError as exc:
        return _error_page(exc)
    return _page("Confirmed", f"<p>Thank you. <b>{html.escape(group.name)}</b> is now active on ACbridge.</p>")
