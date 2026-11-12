import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Role, ServiceRequest, User
from app.schemas import MatchesOut, MatchOut, ScoreBreakdown
from app.security.permissions import require_roles
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
            ) for s in result.ranked
        ],
    )
