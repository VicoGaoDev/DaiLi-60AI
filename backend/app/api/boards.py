from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.board import BoardCreate, BoardListResponse, BoardSummary, BoardUpdate
from app.services.board_service import create_user_board, delete_user_board, list_user_boards, update_user_board

router = APIRouter(prefix="/api/boards", tags=["看板"])


@router.get("", response_model=BoardListResponse)
def list_boards(
    include_stats: bool = Query(True),
    include_previews: bool = Query(True),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_user_boards(
        db,
        user.id,
        include_stats=include_stats,
        include_previews=include_previews,
    )


@router.post("", response_model=BoardSummary, status_code=status.HTTP_201_CREATED)
def create_board(
    body: BoardCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_user_board(db, user.id, body.name)


@router.patch("/{board_id}", response_model=BoardSummary)
def update_board(
    board_id: int,
    body: BoardUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_user_board(db, user.id, board_id, body.name)


@router.delete("/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_board(
    board_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_user_board(db, user.id, board_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
