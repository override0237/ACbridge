import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Role, ServiceRequest, Skill, User
from app.schemas import ServiceRequestIn, ServiceRequestOut
from app.security.authentication import get_current_user
from app.security.permissions import require_roles

router = APIRouter(prefix="/service-requests", tags=["service requests"])


@router.post("", response_model=ServiceRequestOut, status_code=status.HTTP_201_CREATED)
def create_request(payload: ServiceRequestIn, user: User = Depends(require_roles(Role.CUSTOMER)),
                   db: Session = Depends(get_db)) -> ServiceRequest:
    if db.get(Skill, payload.skill_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Skill not found")
    # customer_id and status are set by the server, never by the client.
    service_request = ServiceRequest(customer_id=user.user_id, **payload.model_dump())
    db.add(service_request)
    db.commit()
    return service_request


@router.get("/{request_id}", response_model=ServiceRequestOut)
def get_request(request_id: uuid.UUID, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> ServiceRequest:
    service_request = db.get(ServiceRequest, request_id)
    if service_request is None or (
        service_request.customer_id != user.user_id and user.role != Role.ADMIN.value
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service request not found")
    return service_request
