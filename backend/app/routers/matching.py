import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Role, ServiceRequest, Skill, User
from app.schemas import ContactOut, MatchesOut, MatchOut, ScoreBreakdown
from app.security.permissions import require_roles
from app.services import contact_service
from app.services import matching_service as svc

router = APIRouter(prefix="/matches", tags=["matching"])


@router.get("/{request_id}", response_model=MatchesOut)
def get_matches(
    request_id: uuid.UUID, limit: int = Query(svc.DEFAULT_RESULT_LIMIT, ge=1, le=50),
    user: User = Depends(require_roles(Role.CUSTOMER, Role.ADMIN)), db: Session = Depends(get_db),
) -> MatchesOut:
    service_request = db.get(ServiceRequest, request_id)
    if service_request is None or (service_request.customer_id != user.user_id and user.role != Role.ADMIN.value):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service request not found")
    result = svc.find_matches(db, service_request, limit)
    skill_name = db.get(Skill, service_request.skill_id).skill_name

    def contact_for(artisan) -> ContactOut | None:
        if not artisan.whatsapp_number:   # artisan did not opt in
            return None
        message = contact_service.customer_to_artisan_message(
            artisan.full_name, skill_name, service_request.location, service_request.budget,
            str(service_request.request_id), service_request.needs_inspection)
        return ContactOut(link=contact_service.whatsapp_link(artisan.whatsapp_number, message),
                          tip=contact_service.WHATSAPP_SAFETY_TIP)

    return MatchesOut(
        request_id=request_id, weights=svc.WEIGHTS, service_area_supported=result.service_area_supported,
        excluded_summary=result.excluded_summary, disclaimer=svc.DISCLAIMER,
        matches=[
            MatchOut(
                artisan_id=s.candidate.artisan.artisan_id, full_name=s.candidate.artisan.full_name,
                location=s.candidate.artisan.location, availability_status=s.candidate.artisan.availability_status,
                skill_verification_status=s.candidate.artisan_skill.verification_status,
                typical_price=s.candidate.artisan_skill.typical_price,
                verified_reviews=s.reputation.verified_reviews, reputation_score=s.reputation.reputation_score,
                match_score=round(s.match_score, 2),
                breakdown=ScoreBreakdown(**{k: round(v, 2) for k, v in s.breakdown.items()}),
                contact=contact_for(s.candidate.artisan),
            ) for s in result.ranked
        ],
    )
