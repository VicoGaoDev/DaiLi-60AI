from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.history import HistoryPinToggleRequest, HistoryPinToggleResponse, UserHistoryResponse
from app.services.history_service import delete_user_history_task, get_admin_history_cards, toggle_history_pin

router = APIRouter(prefix="/api/history", tags=["历史记录"])


@router.get("", response_model=UserHistoryResponse)
def list_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    respect_pins: bool = Query(True),
    include_prompt_reverse: bool = Query(True),
    mode: str | None = Query(None, pattern="^(text_generate|image_edit|inpaint|smart_cutout|promptReverse|promptOptimize)$"),
    source: str | None = Query(None, pattern="^(web|app|api)$"),
    model: str | None = Query(None),
    prompt: str | None = Query(None),
    status: str | None = Query(None, pattern="^(pending|processing|success|failed)$"),
    exclude_failed: bool = Query(False),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    board_id: int | None = Query(None),
    board_scope: str | None = Query(None, pattern="^(default|all)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_admin_history_cards(
        db,
        page=page,
        page_size=page_size,
        user_id=user.id,
        include_prompt_reverse=include_prompt_reverse,
        include_restricted_users=True,
        include_deleted_tasks=False,
        mode=mode,
        source=source,
        model=model,
        prompt=prompt,
        status=status,
        exclude_failed=exclude_failed,
        start_date=start_date,
        end_date=end_date,
        board_id=board_id,
        board_scope=board_scope,
        include_provider_diagnostics=False,
    )


@router.delete("/tasks/{task_id}")
def delete_history_task(
    task_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not delete_user_history_task(db, user.id, task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"ok": True}


@router.post("/pins/toggle", response_model=HistoryPinToggleResponse)
def toggle_history_card_pin(
    body: HistoryPinToggleRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return toggle_history_pin(
            db,
            user.id,
            item_type=body.item_type,
            image_id=body.image_id,
            history_id=body.history_id,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的历史卡片标识")
    except LookupError:
        raise HTTPException(status_code=404, detail="历史卡片不存在")
