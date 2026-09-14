from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_superadmin
from app.database import get_db
from app.models.user import User
from app.schemas.external_api_config import (
    ExternalApiConfigCreate,
    ExternalApiConfigOut,
    ExternalApiSceneBindingCreate,
    ExternalApiSceneBindingMetaUpdate,
    ExternalApiSceneBindingOut,
    ExternalApiSceneBindingStatusUpdate,
    ExternalApiSceneBindingUpdate,
    ExternalApiConfigStatusUpdate,
    ExternalApiConfigTestResult,
    GenerationModelOptionOut,
    ExternalApiConfigUpdate,
    TaskSceneConfigOut,
)
from app.services.external_api_config_service import (
    create_config,
    delete_config,
    delete_scene_binding,
    create_scene_binding,
    list_scene_bindings,
    list_public_task_scene_configs,
    list_generation_models,
    list_configs,
    set_scene_binding_status,
    set_scene_binding,
    set_config_status,
    test_external_api_config,
    update_scene_binding_meta,
    update_config,
)

router = APIRouter(prefix="/api/admin/external-api-configs", tags=["外部接口配置"])
scene_router = APIRouter(prefix="/api/admin/external-api-scene-bindings", tags=["外部接口场景绑定"])
public_router = APIRouter(prefix="/api/config", tags=["公开配置"])


@router.get("", response_model=list[ExternalApiConfigOut])
def get_external_api_configs(
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return list_configs(db)


@public_router.get("/generation-models", response_model=list[GenerationModelOptionOut])
def get_generation_models(db: Session = Depends(get_db)):
    return list_generation_models(db)


@public_router.get("/task-scenes", response_model=list[TaskSceneConfigOut])
def get_task_scenes(db: Session = Depends(get_db)):
    return list_public_task_scene_configs(db)


@router.post("", response_model=ExternalApiConfigOut)
def create_external_api_config(
    body: ExternalApiConfigCreate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return create_config(db, body)


@router.post("/test", response_model=ExternalApiConfigTestResult)
def test_external_api_config_endpoint(
    body: ExternalApiConfigCreate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return test_external_api_config(db, body)


@router.put("/{config_id}", response_model=ExternalApiConfigOut)
def update_external_api_config(
    config_id: int,
    body: ExternalApiConfigUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return update_config(db, config_id, body)


@router.patch("/{config_id}/status", response_model=ExternalApiConfigOut)
def patch_external_api_config_status(
    config_id: int,
    body: ExternalApiConfigStatusUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return set_config_status(db, config_id, body.status)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_external_api_config(
    config_id: int,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    delete_config(db, config_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@scene_router.get("", response_model=list[ExternalApiSceneBindingOut])
def get_external_api_scene_bindings(
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return list_scene_bindings(db)


@scene_router.post("", response_model=ExternalApiSceneBindingOut)
def create_external_api_scene_binding(
    body: ExternalApiSceneBindingCreate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return create_scene_binding(db, body)


@scene_router.put("/{scene_key}", response_model=ExternalApiSceneBindingOut)
def update_external_api_scene_binding(
    scene_key: str,
    body: ExternalApiSceneBindingUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return set_scene_binding(db, scene_key, body)


@scene_router.patch("/{scene_key}/meta", response_model=ExternalApiSceneBindingOut)
def patch_external_api_scene_binding_meta(
    scene_key: str,
    body: ExternalApiSceneBindingMetaUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return update_scene_binding_meta(db, scene_key, body)


@scene_router.patch("/{scene_key}/status", response_model=ExternalApiSceneBindingOut)
def patch_external_api_scene_binding_status(
    scene_key: str,
    body: ExternalApiSceneBindingStatusUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return set_scene_binding_status(db, scene_key, body)


@scene_router.delete("/{scene_key}", status_code=status.HTTP_204_NO_CONTENT)
def remove_external_api_scene_binding(
    scene_key: str,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    delete_scene_binding(db, scene_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
