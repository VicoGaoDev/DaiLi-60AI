import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.database import get_db
from app.models.template import Template
from app.models.template_tag import TemplateTag
from app.models.template_tag_relation import TemplateTagRelation
from app.models.user import User
from app.schemas.template import (
    TemplateCreate,
    TemplateDetailOut,
    TemplateListItemOut,
    TemplateListResponse,
    TemplateTagPayload,
    TemplateTagOut,
    TemplateUpdate,
)
from app.services.image_delivery_service import get_optional_cos_config, serialize_asset_urls

router = APIRouter(prefix="/api/templates", tags=["创意模版"])


def _normalize_tag_name(name: str) -> str:
    return (name or "").strip()[:50]


def _normalize_tag_names(tag_names: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for name in tag_names:
        normalized = _normalize_tag_name(name)
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(normalized)
    return result


def _serialize_tag(tag: TemplateTag) -> dict:
    return {
        "id": tag.id,
        "name": tag.name,
        "template_count": len(tag.template_relations),
    }


def _serialize_template_list_item(template: Template, *, cos_config=None) -> dict:
    result_asset = serialize_asset_urls(template.result_image or "", cos_config=cos_config)
    return {
        "id": template.id,
        "prompt": template.prompt or "",
        "model": template.model or "",
        "result_image": result_asset["image_url"],
        "result_image_thumb": result_asset["thumb_url"],
        "sort_order": template.sort_order or 0,
        "size": template.size,
        "resolution": template.resolution or "",
        "custom_size": template.custom_size or "",
        "num_images": 1,
        "tags": [
            {"id": rel.tag.id, "name": rel.tag.name}
            for rel in sorted(template.tag_relations, key=lambda rel: rel.tag.name.lower())
            if rel.tag
        ],
        "created_at": template.created_at,
    }


def _serialize_template_detail(template: Template, *, cos_config=None) -> dict:
    reference_assets = [
        serialize_asset_urls(url, cos_config=cos_config)
        for url in json.loads(template.reference_images or "[]")
    ]
    return {
        **_serialize_template_list_item(template, cos_config=cos_config),
        "reference_images": [asset["image_url"] for asset in reference_assets],
        "reference_image_thumbs": [asset["thumb_url"] for asset in reference_assets],
    }


def _sync_template_tags(db: Session, template: Template, tag_names: list[str]):
    normalized_names = _normalize_tag_names(tag_names)
    template.tag_relations.clear()
    db.flush()

    for tag_name in normalized_names:
        tag = db.query(TemplateTag).filter(TemplateTag.name == tag_name).first()
        if not tag:
            tag = TemplateTag(name=tag_name)
            db.add(tag)
            db.flush()
        template.tag_relations.append(TemplateTagRelation(tag_id=tag.id))


@router.get("", response_model=TemplateListResponse)
def list_templates(
    tag_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    cos_config = get_optional_cos_config(db)
    query = db.query(Template).order_by(Template.sort_order.desc(), Template.created_at.desc())
    if tag_id is not None:
        query = query.join(TemplateTagRelation).filter(TemplateTagRelation.tag_id == tag_id)
    total = query.count()
    templates = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "items": [_serialize_template_list_item(template, cos_config=cos_config) for template in templates],
    }


@router.get("/tags", response_model=list[TemplateTagOut])
def list_template_tags(db: Session = Depends(get_db)):
    tags = db.query(TemplateTag).order_by(TemplateTag.name.asc()).all()
    return [_serialize_tag(tag) for tag in tags]


@router.post("/tags", response_model=TemplateTagOut)
def create_template_tag(
    body: TemplateTagPayload,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tag_name = _normalize_tag_name(body.name)
    if not tag_name:
        raise HTTPException(status_code=400, detail="标签名称不能为空")

    existing_tag = db.query(TemplateTag).filter(TemplateTag.name == tag_name).first()
    if existing_tag:
        raise HTTPException(status_code=400, detail="标签已存在")

    tag = TemplateTag(name=tag_name)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return _serialize_tag(tag)


@router.put("/tags/{tag_id}", response_model=TemplateTagOut)
def update_template_tag(
    tag_id: int,
    body: TemplateTagPayload,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tag = db.query(TemplateTag).filter(TemplateTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")

    tag_name = _normalize_tag_name(body.name)
    if not tag_name:
        raise HTTPException(status_code=400, detail="标签名称不能为空")

    existing_tag = db.query(TemplateTag).filter(TemplateTag.name == tag_name, TemplateTag.id != tag_id).first()
    if existing_tag:
        raise HTTPException(status_code=400, detail="标签已存在")

    tag.name = tag_name
    db.commit()
    db.refresh(tag)
    return _serialize_tag(tag)


@router.delete("/tags/{tag_id}")
def delete_template_tag(
    tag_id: int,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    tag = db.query(TemplateTag).filter(TemplateTag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")

    db.delete(tag)
    db.commit()
    return {"message": "删除成功"}


@router.get("/admin/list", response_model=list[TemplateListItemOut])
def list_admin_templates(
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    cos_config = get_optional_cos_config(db)
    templates = db.query(Template).order_by(Template.sort_order.desc(), Template.created_at.desc()).all()
    return [_serialize_template_list_item(template, cos_config=cos_config) for template in templates]


@router.get("/{template_id}", response_model=TemplateDetailOut)
def get_template_detail(template_id: int, db: Session = Depends(get_db)):
    cos_config = get_optional_cos_config(db)
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模版不存在")
    return _serialize_template_detail(template, cos_config=cos_config)


@router.post("", response_model=TemplateDetailOut)
def create_template(
    body: TemplateCreate,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="提示词不能为空")
    template = Template(
        prompt=body.prompt.strip(),
        model=body.model.strip() or "banana_pro",
        reference_images=json.dumps(body.reference_images or []),
        size=body.size,
        resolution=body.resolution,
        custom_size=body.custom_size.strip(),
        num_images=1,
        result_image=body.result_image,
        sort_order=body.sort_order,
    )
    db.add(template)
    db.flush()
    _sync_template_tags(db, template, body.tag_names)
    db.commit()
    db.refresh(template)
    return _serialize_template_detail(template, cos_config=get_optional_cos_config(db))


@router.put("/{template_id}", response_model=TemplateDetailOut)
def update_template(
    template_id: int,
    body: TemplateUpdate,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模版不存在")
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="提示词不能为空")

    template.prompt = body.prompt.strip()
    template.model = body.model.strip() or "banana_pro"
    template.reference_images = json.dumps(body.reference_images or [])
    template.size = body.size
    template.resolution = body.resolution
    template.custom_size = body.custom_size.strip()
    template.num_images = 1
    template.result_image = body.result_image
    template.sort_order = body.sort_order
    _sync_template_tags(db, template, body.tag_names)
    db.commit()
    db.refresh(template)
    return _serialize_template_detail(template, cos_config=get_optional_cos_config(db))


@router.delete("/{template_id}")
def delete_template(
    template_id: int,
    _user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    template = db.query(Template).filter(Template.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="模版不存在")
    db.delete(template)
    db.commit()
    return {"message": "删除成功"}
