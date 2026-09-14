from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.user_prompt import UserPrompt
from app.models.user_prompt_category import UserPromptCategory

MAX_CATEGORY_NAME_LENGTH = 100
MAX_PROMPT_TITLE_LENGTH = 255
MAX_PROMPT_CONTENT_LENGTH = 10000
UNCATEGORIZED_FILTER_ID = 0


def _normalize_category_name(name: str | None) -> str:
    normalized = (name or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类名称不能为空")
    if len(normalized) > MAX_CATEGORY_NAME_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"分类名称不能超过 {MAX_CATEGORY_NAME_LENGTH} 个字符",
        )
    return normalized


def _normalize_prompt_title(title: str | None) -> str:
    normalized = (title or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="标题不能为空")
    if len(normalized) > MAX_PROMPT_TITLE_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"标题不能超过 {MAX_PROMPT_TITLE_LENGTH} 个字符",
        )
    return normalized


def _normalize_prompt_content(content: str | None) -> str:
    normalized = (content or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="提示词内容不能为空")
    if len(normalized) > MAX_PROMPT_CONTENT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"提示词内容不能超过 {MAX_PROMPT_CONTENT_LENGTH} 个字符",
        )
    return normalized


def _get_user_prompt_category_or_404(db: Session, user_id: int, category_id: int) -> UserPromptCategory:
    category = (
        db.query(UserPromptCategory)
        .filter(UserPromptCategory.id == category_id, UserPromptCategory.user_id == user_id)
        .first()
    )
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提示词分类不存在")
    return category


def _normalize_category_id(db: Session, user_id: int, category_id: int | None) -> int | None:
    if category_id in (None, UNCATEGORIZED_FILTER_ID):
        return None
    return _get_user_prompt_category_or_404(db, user_id, category_id).id


def _serialize_user_prompt(prompt: UserPrompt) -> dict:
    category_name = prompt.category.name if prompt.category else ""
    return {
        "id": prompt.id,
        "category_id": prompt.category_id,
        "category_name": category_name,
        "title": prompt.title or "",
        "content": prompt.content or "",
        "created_at": prompt.created_at,
        "updated_at": prompt.updated_at,
    }


def list_user_prompt_categories(db: Session, user_id: int) -> dict:
    categories = (
        db.query(UserPromptCategory)
        .filter(UserPromptCategory.user_id == user_id)
        .order_by(UserPromptCategory.sort_order.asc(), UserPromptCategory.updated_at.desc(), UserPromptCategory.id.desc())
        .all()
    )
    stat_rows = (
        db.query(
            UserPrompt.category_id,
            func.count(UserPrompt.id).label("prompt_count"),
        )
        .filter(
            UserPrompt.user_id == user_id,
            UserPrompt.is_deleted.is_(False),
        )
        .group_by(UserPrompt.category_id)
        .all()
    )
    count_map = {
        row.category_id: int(row.prompt_count or 0)
        for row in stat_rows
    }
    return {
        "items": [
            {
                "id": category.id,
                "name": category.name or "未命名分类",
                "sort_order": int(category.sort_order or 0),
                "prompt_count": count_map.get(category.id, 0),
                "updated_at": category.updated_at,
            }
            for category in categories
        ],
        "uncategorized_count": count_map.get(None, 0),
    }


def create_user_prompt_category(db: Session, user_id: int, name: str) -> dict:
    normalized_name = _normalize_category_name(name)
    exists = (
        db.query(UserPromptCategory.id)
        .filter(UserPromptCategory.user_id == user_id, UserPromptCategory.name == normalized_name)
        .first()
    )
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类名称已存在")

    max_sort_order = db.query(func.max(UserPromptCategory.sort_order)).filter(UserPromptCategory.user_id == user_id).scalar()
    category = UserPromptCategory(
        user_id=user_id,
        name=normalized_name,
        sort_order=int(max_sort_order or 0) + 1,
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return {
        "id": category.id,
        "name": category.name,
        "sort_order": int(category.sort_order or 0),
        "prompt_count": 0,
        "updated_at": category.updated_at,
    }


def update_user_prompt_category(db: Session, user_id: int, category_id: int, name: str) -> dict:
    category = _get_user_prompt_category_or_404(db, user_id, category_id)
    normalized_name = _normalize_category_name(name)
    exists = (
        db.query(UserPromptCategory.id)
        .filter(
            UserPromptCategory.user_id == user_id,
            UserPromptCategory.name == normalized_name,
            UserPromptCategory.id != category.id,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="分类名称已存在")

    category.name = normalized_name
    db.commit()
    db.refresh(category)
    active_prompt_count = int(
        db.query(func.count(UserPrompt.id))
        .filter(
            UserPrompt.user_id == user_id,
            UserPrompt.category_id == category.id,
            UserPrompt.is_deleted.is_(False),
        )
        .scalar() or 0
    )
    return {
        "id": category.id,
        "name": category.name,
        "sort_order": int(category.sort_order or 0),
        "prompt_count": active_prompt_count,
        "updated_at": category.updated_at,
    }


def delete_user_prompt_category(db: Session, user_id: int, category_id: int) -> None:
    category = _get_user_prompt_category_or_404(db, user_id, category_id)
    active_prompts = (
        db.query(func.count(UserPrompt.id))
        .filter(
            UserPrompt.user_id == user_id,
            UserPrompt.category_id == category.id,
            UserPrompt.is_deleted.is_(False),
        )
        .scalar()
    )
    if int(active_prompts or 0) > 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该分类下仍有提示词，请先删除或移动提示词")
    db.delete(category)
    db.commit()


def list_user_prompts(
    db: Session,
    user_id: int,
    *,
    category_id: int | None = None,
    keyword: str | None = None,
    limit: int = 100,
) -> dict:
    normalized_category_id = None if category_id is None else _normalize_category_id(db, user_id, category_id)
    trimmed_keyword = (keyword or "").strip()

    query = (
        db.query(UserPrompt)
        .options(joinedload(UserPrompt.category))
        .filter(
            UserPrompt.user_id == user_id,
            UserPrompt.is_deleted.is_(False),
        )
    )
    if category_id == UNCATEGORIZED_FILTER_ID:
        query = query.filter(UserPrompt.category_id.is_(None))
    elif normalized_category_id is not None:
        query = query.filter(UserPrompt.category_id == normalized_category_id)
    if trimmed_keyword:
        query = query.filter(
            or_(
                UserPrompt.title.like(f"%{trimmed_keyword}%"),
                UserPrompt.content.like(f"%{trimmed_keyword}%"),
            )
        )

    safe_limit = max(1, min(limit, 200))
    items = (
        query.order_by(UserPrompt.updated_at.desc(), UserPrompt.id.desc())
        .limit(safe_limit)
        .all()
    )
    total = int(query.order_by(None).count())
    return {
        "items": [_serialize_user_prompt(item) for item in items],
        "total": total,
    }


def create_user_prompt(
    db: Session,
    user_id: int,
    *,
    category_id: int | None = None,
    title: str,
    content: str,
) -> dict:
    prompt = UserPrompt(
        user_id=user_id,
        category_id=_normalize_category_id(db, user_id, category_id),
        title=_normalize_prompt_title(title),
        content=_normalize_prompt_content(content),
    )
    db.add(prompt)
    db.commit()
    db.refresh(prompt)
    prompt = get_user_prompt_or_404(db, user_id, prompt.id)
    return _serialize_user_prompt(prompt)


def get_user_prompt_or_404(db: Session, user_id: int, prompt_id: int) -> UserPrompt:
    prompt = (
        db.query(UserPrompt)
        .options(joinedload(UserPrompt.category))
        .filter(
            UserPrompt.id == prompt_id,
            UserPrompt.user_id == user_id,
            UserPrompt.is_deleted.is_(False),
        )
        .first()
    )
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提示词不存在")
    return prompt


def update_user_prompt(
    db: Session,
    user_id: int,
    prompt_id: int,
    *,
    category_id: int | None = None,
    update_category: bool = False,
    title: str | None = None,
    content: str | None = None,
) -> dict:
    prompt = get_user_prompt_or_404(db, user_id, prompt_id)
    if update_category:
        prompt.category_id = _normalize_category_id(db, user_id, category_id)
    if title is not None:
        prompt.title = _normalize_prompt_title(title)
    if content is not None:
        prompt.content = _normalize_prompt_content(content)
    db.commit()
    prompt = get_user_prompt_or_404(db, user_id, prompt_id)
    return _serialize_user_prompt(prompt)


def delete_user_prompt(db: Session, user_id: int, prompt_id: int) -> dict:
    prompt = (
        db.query(UserPrompt)
        .filter(UserPrompt.id == prompt_id, UserPrompt.user_id == user_id)
        .first()
    )
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提示词不存在")
    if prompt.is_deleted:
        return {"ok": True}

    prompt.is_deleted = True
    prompt.deleted_at = func.now()
    db.commit()
    return {"ok": True}
