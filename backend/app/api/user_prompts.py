from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.user_prompt import (
    UserPromptCategoryCreate,
    UserPromptCategoryListResponse,
    UserPromptCategorySummary,
    UserPromptCategoryUpdate,
    UserPromptCreateRequest,
    UserPromptDeleteResponse,
    UserPromptListResponse,
    UserPromptSummary,
    UserPromptUpdateRequest,
)
from app.services.user_prompt_service import (
    create_user_prompt,
    create_user_prompt_category,
    delete_user_prompt,
    delete_user_prompt_category,
    list_user_prompt_categories,
    list_user_prompts,
    update_user_prompt,
    update_user_prompt_category,
)

router = APIRouter(prefix="/api/user-prompts", tags=["提示词库"])
category_router = APIRouter(prefix="/api/user-prompts/categories", tags=["提示词分类"])


@category_router.get("", response_model=UserPromptCategoryListResponse)
def get_categories(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_user_prompt_categories(db, user.id)


@category_router.post("", response_model=UserPromptCategorySummary, status_code=status.HTTP_201_CREATED)
def create_category(
    body: UserPromptCategoryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_user_prompt_category(db, user.id, body.name)


@category_router.patch("/{category_id}", response_model=UserPromptCategorySummary)
def patch_category(
    category_id: int,
    body: UserPromptCategoryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return update_user_prompt_category(db, user.id, category_id, body.name)


@category_router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_category(
    category_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    delete_user_prompt_category(db, user.id, category_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=UserPromptListResponse)
def get_prompts(
    category_id: int | None = Query(default=None),
    keyword: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return list_user_prompts(
        db,
        user.id,
        category_id=category_id,
        keyword=keyword,
        limit=limit,
    )


@router.post("", response_model=UserPromptSummary, status_code=status.HTTP_201_CREATED)
def create_prompt(
    body: UserPromptCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return create_user_prompt(
        db,
        user.id,
        category_id=body.category_id,
        title=body.title,
        content=body.content,
    )


@router.patch("/{prompt_id}", response_model=UserPromptSummary)
def patch_prompt(
    prompt_id: int,
    body: UserPromptUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payload = body.model_dump(exclude_unset=True)
    return update_user_prompt(
        db,
        user.id,
        prompt_id,
        category_id=payload.get("category_id"),
        update_category="category_id" in payload,
        title=payload.get("title"),
        content=payload.get("content"),
    )


@router.delete("/{prompt_id}", response_model=UserPromptDeleteResponse)
def remove_prompt(
    prompt_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return delete_user_prompt(db, user.id, prompt_id)
