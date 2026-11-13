"""Review endpoints live with their resources for readable URLs:
  POST /jobs/{job_id}/reviews            -> routers/jobs.py
  GET  /artisans/{artisan_id}/reputation -> routers/artisans.py
This module lists a customer's own reviews, which is handy for the UI."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Review, Role, User
from app.schemas import ReviewOut
from app.security.permissions import require_roles

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/mine", response_model=list[ReviewOut])
def my_reviews(user: User = Depends(require_roles(Role.CUSTOMER)), db: Session = Depends(get_db)) -> list[Review]:
    return list(db.scalars(select(Review).where(Review.reviewer_id == user.user_id).order_by(Review.created_at.desc())))
