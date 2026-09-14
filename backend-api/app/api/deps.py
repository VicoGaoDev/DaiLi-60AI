from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db
from app.logging_utils import set_request_context
from app.models.user import User
from app.services.business_id_service import user_external_id
from app.services.user_api_key_service import authenticate_user_api_key

security = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    api_key = request.headers.get("x-api-key", "").strip()
    if not api_key and credentials:
        api_key = (credentials.credentials or "").strip()
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 API Key")

    user = authenticate_user_api_key(db, api_key)
    external_id = user_external_id(user)
    request.state.user_id = external_id
    set_request_context(getattr(request.state, "request_id", "-"), external_id)
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("admin", "superadmin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def require_superadmin(user: User = Depends(get_current_user)) -> User:
    if user.role != "superadmin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要超级管理员权限")
    return user
