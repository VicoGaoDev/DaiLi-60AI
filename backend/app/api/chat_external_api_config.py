from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_superadmin
from app.database import get_db
from app.models.user import User
from app.schemas.chat_external_api_config import (
    ChatExternalApiConfigCreate,
    ChatExternalApiConfigOut,
    ChatExternalApiConfigStatusUpdate,
    ChatExternalApiConfigTestResult,
    ChatExternalApiConfigUpdate,
    ChatExternalApiSceneBindingCreate,
    ChatExternalApiSceneBindingMetaUpdate,
    ChatExternalApiSceneBindingOut,
    ChatExternalApiSceneBindingStatusUpdate,
    ChatExternalApiSceneBindingUpdate,
    ChatGenerationModelOptionOut,
)
from app.services.chat_external_api_config_service import (
    create_chat_config,
    create_chat_scene_binding,
    delete_chat_config,
    delete_chat_scene_binding,
    list_chat_configs,
    list_chat_generation_models,
    list_chat_scene_bindings,
    set_chat_config_status,
    set_chat_scene_binding_status,
    test_chat_external_api_config,
    update_chat_config,
    update_chat_scene_binding,
    update_chat_scene_binding_meta,
)

router = APIRouter(prefix="/api/admin/chat-external-api-configs", tags=["对话接口配置"])
scene_router = APIRouter(prefix="/api/admin/chat-external-api-scene-bindings", tags=["对话接口场景绑定"])
public_router = APIRouter(prefix="/api/config", tags=["对话公开配置"])


@router.get("", response_model=list[ChatExternalApiConfigOut])
def get_chat_external_api_configs(
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return list_chat_configs(db)


@router.post("", response_model=ChatExternalApiConfigOut)
def create_chat_external_api_config_endpoint(
    body: ChatExternalApiConfigCreate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return create_chat_config(db, body)


@router.post("/test", response_model=ChatExternalApiConfigTestResult)
def test_chat_external_api_config_endpoint(
    body: ChatExternalApiConfigCreate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return test_chat_external_api_config(db, body)


@router.put("/{config_id}", response_model=ChatExternalApiConfigOut)
def update_chat_external_api_config_endpoint(
    config_id: int,
    body: ChatExternalApiConfigUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return update_chat_config(db, config_id, body)


@router.patch("/{config_id}/status", response_model=ChatExternalApiConfigOut)
def patch_chat_external_api_config_status(
    config_id: int,
    body: ChatExternalApiConfigStatusUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return set_chat_config_status(db, config_id, body.status)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_chat_external_api_config(
    config_id: int,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    delete_chat_config(db, config_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@scene_router.get("", response_model=list[ChatExternalApiSceneBindingOut])
def get_chat_external_api_scene_bindings(
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return list_chat_scene_bindings(db)


@scene_router.post("", response_model=ChatExternalApiSceneBindingOut)
def create_chat_external_api_scene_binding_endpoint(
    body: ChatExternalApiSceneBindingCreate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return create_chat_scene_binding(db, body)


@scene_router.put("/{scene_key}", response_model=ChatExternalApiSceneBindingOut)
def update_chat_external_api_scene_binding_endpoint(
    scene_key: str,
    body: ChatExternalApiSceneBindingUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return update_chat_scene_binding(db, scene_key, body)


@scene_router.patch("/{scene_key}/meta", response_model=ChatExternalApiSceneBindingOut)
def patch_chat_external_api_scene_binding_meta(
    scene_key: str,
    body: ChatExternalApiSceneBindingMetaUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return update_chat_scene_binding_meta(db, scene_key, body)


@scene_router.patch("/{scene_key}/status", response_model=ChatExternalApiSceneBindingOut)
def patch_chat_external_api_scene_binding_status(
    scene_key: str,
    body: ChatExternalApiSceneBindingStatusUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return set_chat_scene_binding_status(db, scene_key, body.status)


@scene_router.delete("/{scene_key}", status_code=status.HTTP_204_NO_CONTENT)
def remove_chat_external_api_scene_binding(
    scene_key: str,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    delete_chat_scene_binding(db, scene_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_router.get("/chat-models", response_model=list[ChatGenerationModelOptionOut])
def get_chat_models(db: Session = Depends(get_db)):
    return list_chat_generation_models(db)
