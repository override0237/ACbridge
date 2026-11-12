"""Role-based access control helpers (authorisation, as opposed to authentication)."""
from fastapi import Depends, HTTPException, status

from app.models import Role, User
from app.security.authentication import get_current_user


def require_roles(*allowed: Role):
    """FastAPI dependency factory: `Depends(require_roles(Role.ADMIN))`."""
    allowed_values = {r.value for r in allowed}

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_values:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"This action requires one of the roles: {sorted(allowed_values)}"
            )
        return user

    return dependency
