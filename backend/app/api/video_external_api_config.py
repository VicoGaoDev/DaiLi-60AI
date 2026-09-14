from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import require_superadmin
from app.database import get_db
from app.models.user import User
from app.schemas.video_external_api_config import (
    VideoExternalApiConfigCreate,
    VideoExternalApiConfigOut,
    VideoExternalApiConfigStatusUpdate,
    VideoExternalApiConfigTestResult,
    VideoExternalApiConfigUpdate,
    VideoExternalApiSceneBindingCreate,
    VideoExternalApiSceneBindingMetaUpdate,
    VideoExternalApiSceneBindingOut,
    VideoExternalApiSceneBindingStatusUpdate,
    VideoExternalApiSceneBindingUpdate,
    VideoGenerationModelOptionOut,
    VideoTaskSceneConfigOut,
)
from app.services.video_external_api_config_service import (
    create_video_config,
    create_video_scene_binding,
    delete_video_config,
    delete_video_scene_binding,
    list_public_video_task_scene_configs,
    list_video_configs,
    list_video_generation_models,
    list_video_scene_bindings,
    set_video_config_status,
    set_video_scene_binding_status,
    test_video_external_api_config,
    update_video_config,
    update_video_scene_binding,
    update_video_scene_binding_meta,
)

router = APIRouter(prefix="/api/admin/video-external-api-configs", tags=["视频接口配置"])
scene_router = APIRouter(prefix="/api/admin/video-external-api-scene-bindings", tags=["视频接口场景绑定"])
public_router = APIRouter(prefix="/api/config", tags=["视频公开配置"])


@router.get("", response_model=list[VideoExternalApiConfigOut])
def get_video_external_api_configs(
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return list_video_configs(db)


@router.post("", response_model=VideoExternalApiConfigOut)
def create_video_external_api_config_endpoint(
    body: VideoExternalApiConfigCreate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return create_video_config(db, body)


@router.post("/test", response_model=VideoExternalApiConfigTestResult)
def test_video_external_api_config_endpoint(
    body: VideoExternalApiConfigCreate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return test_video_external_api_config(db, body)


@router.put("/{config_id}", response_model=VideoExternalApiConfigOut)
def update_video_external_api_config_endpoint(
    config_id: int,
    body: VideoExternalApiConfigUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return update_video_config(db, config_id, body)


@router.patch("/{config_id}/status", response_model=VideoExternalApiConfigOut)
def patch_video_external_api_config_status(
    config_id: int,
    body: VideoExternalApiConfigStatusUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return set_video_config_status(db, config_id, body.status)


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_video_external_api_config(
    config_id: int,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    delete_video_config(db, config_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@scene_router.get("", response_model=list[VideoExternalApiSceneBindingOut])
def get_video_external_api_scene_bindings(
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return list_video_scene_bindings(db)


@scene_router.post("", response_model=VideoExternalApiSceneBindingOut)
def create_video_external_api_scene_binding_endpoint(
    body: VideoExternalApiSceneBindingCreate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return create_video_scene_binding(db, body)


@scene_router.put("/{scene_key}", response_model=VideoExternalApiSceneBindingOut)
def update_video_external_api_scene_binding_endpoint(
    scene_key: str,
    body: VideoExternalApiSceneBindingUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return update_video_scene_binding(db, scene_key, body)


@scene_router.patch("/{scene_key}/meta", response_model=VideoExternalApiSceneBindingOut)
def patch_video_external_api_scene_binding_meta(
    scene_key: str,
    body: VideoExternalApiSceneBindingMetaUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return update_video_scene_binding_meta(db, scene_key, body)


@scene_router.patch("/{scene_key}/status", response_model=VideoExternalApiSceneBindingOut)
def patch_video_external_api_scene_binding_status(
    scene_key: str,
    body: VideoExternalApiSceneBindingStatusUpdate,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    return set_video_scene_binding_status(db, scene_key, body.status)


@scene_router.delete("/{scene_key}", status_code=status.HTTP_204_NO_CONTENT)
def remove_video_external_api_scene_binding(
    scene_key: str,
    _user: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    delete_video_scene_binding(db, scene_key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@public_router.get("/video-generation-models", response_model=list[VideoGenerationModelOptionOut])
def get_video_generation_models(db: Session = Depends(get_db)):
    return list_video_generation_models(db)


@public_router.get("/video-task-scenes", response_model=list[VideoTaskSceneConfigOut])
def get_video_task_scenes(db: Session = Depends(get_db)):
    return list_public_video_task_scene_configs(db)
