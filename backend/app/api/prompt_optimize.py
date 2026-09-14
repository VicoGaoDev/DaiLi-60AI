from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.prompt_optimize import PromptOptimizeRequest, PromptOptimizeResponse
from app.services.prompt_optimize_service import optimize_prompt

router = APIRouter(prefix="/api/prompt-optimize", tags=["提示词优化"])


@router.post("", response_model=PromptOptimizeResponse)
def prompt_optimize(
    body: PromptOptimizeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prompt = optimize_prompt(
        db,
        user.id,
        body.prompt,
        body.reference_images,
        style_name=body.style_name,
        style_prompt=body.style_prompt,
    )
    return PromptOptimizeResponse(prompt=prompt)
