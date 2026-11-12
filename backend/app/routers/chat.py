"""Job chat endpoints. See services/chat_service.py for the rules."""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import JobMessage, Role, User
from app.schemas import ChatMessageIn, ChatMessageOut, ChatSendOut
from app.security.authentication import get_current_user
from app.security.permissions import require_roles
from app.security.rate_limit import rate_limit
from app.services import chat_service, payment_service

router = APIRouter(prefix="/jobs/{job_id}/messages", tags=["chat"])


def message_out(message: JobMessage) -> ChatMessageOut:
    price = message.proposed_price
    commission = payment_service.compute_commission(price) if price is not None else None
    return ChatMessageOut(
        message_id=message.message_id, job_id=message.job_id, sender_role=message.sender_role, body=message.body,
        created_at=message.created_at, proposed_price=price, commission_if_agreed=commission,
        artisan_receives_if_agreed=None if price is None else price - commission,
    )


@router.get("", response_model=list[ChatMessageOut])
def list_messages(job_id: uuid.UUID, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> list[ChatMessageOut]:
    return [message_out(m) for m in chat_service.list_messages(db, user, job_id)]


@router.post("", response_model=ChatSendOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("chat", 60, 60))])
def send_message(job_id: uuid.UUID, payload: ChatMessageIn,
                 user: User = Depends(require_roles(Role.CUSTOMER, Role.ARTISAN)),
                 db: Session = Depends(get_db)) -> ChatSendOut:
    """Customer: end a message with an amount and currency (e.g. `9000 FCFA`) to propose that price."""
    result = chat_service.send_message(db, user, job_id, payload.body)
    return ChatSendOut(message=message_out(result.message), price_status=result.price_status)
