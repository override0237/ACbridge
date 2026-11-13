from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.security.authentication import create_access_token, hash_password, verify_password
from app.security.rate_limit import rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit("register", 10, 3600))])
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> User:
    user = User(phone=payload.phone, password_hash=hash_password(payload.password), role=payload.role)
    db.add(user)
    try:
        db.commit()  # UNIQUE(phone) decides - no check-then-insert race
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "This phone number is already registered")
    return user


@router.post("/login", response_model=TokenOut, dependencies=[Depends(rate_limit("login", 10, 300))])
def login(payload: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.phone == payload.phone))
    # One generic message for "unknown phone" and "wrong password": no account enumeration.
    if not verify_password(payload.password, user.password_hash if user else None) or user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect phone number or password")
    return TokenOut(access_token=create_access_token(user), user_id=user.user_id, role=user.role)
