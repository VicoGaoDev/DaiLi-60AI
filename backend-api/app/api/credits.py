from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.services.admin_service import get_credit_logs

router = APIRouter(prefix="/api/credits", tags=["积分"])


@router.get("/logs")
def my_credit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    direction: Optional[str] = Query(None, pattern="^(increase|decrease)$"),
    mode: Optional[str] = Query(None, pattern="^(text_generate|image_edit|inpaint|promptReverse|manual|redeem)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_credit_logs(
        db,
        user_id=user.id,
        page=page,
        page_size=page_size,
        start_date=start_date,
        end_date=end_date,
        direction=direction,
        mode=mode,
    )
