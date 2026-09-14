from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.prompt_reverse import PromptReverseRequest, PromptReverseResponse
from app.services.prompt_reverse_service import reverse_prompt_from_image

router = APIRouter(prefix="/api/prompt-reverse", tags=["提示词反推"])


@router.post("", response_model=PromptReverseResponse)
def reverse_prompt(
    body: PromptReverseRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    prompt = reverse_prompt_from_image(db, user.id, body.image_url)
    return PromptReverseResponse(prompt=prompt)
