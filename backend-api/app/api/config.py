from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.external_api_config import GenerationModelOptionOut, TaskSceneConfigOut
from app.services.external_api_config_service import list_generation_models, list_public_task_scene_configs

router = APIRouter(prefix="/api/config", tags=["公开配置"])


@router.get("/generation-models", response_model=list[GenerationModelOptionOut])
def get_generation_models(db: Session = Depends(get_db)):
    return list_generation_models(db)


@router.get("/task-scenes", response_model=list[TaskSceneConfigOut])
def get_task_scenes(db: Session = Depends(get_db)):
    return [
        item
        for item in list_public_task_scene_configs(db)
        if item.scene_type in {"generate", "image_edit"}
    ]
