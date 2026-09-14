import json

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models.prompt_optimize_task import PromptOptimizeTask
from app.models.user import User
from app.services.cos_service import load_image_as_data_url
from app.services.external_api_config_service import (
    SCENE_PROMPT_OPTIMIZE,
    build_external_request_kwargs,
    build_secret_variables,
    get_scene_credit_cost,
    render_config,
    require_scene_config,
)
from app.services.prompt_reverse_service import _extract_prompt_text, _is_credit_exempt_user
from app.services.user_credit_service import change_user_credit_balance, get_user_credit_balance

PROMPT_OPTIMIZE_MODE = "promptOptimize"
PROMPT_OPTIMIZE_MODEL = "提示词优化"
PROMPT_OPTIMIZE_CREDIT_LOG_DESCRIPTION = "提示词优化"

PROMPT_OPTIMIZE_TEXT = (
    "你是一名专业的 AI 绘画提示词优化助手。请在保留用户核心创意的前提下，"
    "结合参考图信息优化这段提示词，使其更适合图像生成模型理解。"
    "输出一段可直接用于生图的中文提示词，不要解释，不要分点。"
)


def _parse_data_url_parts(data_url: str) -> tuple[str, str]:
    prefix, sep, encoded = data_url.partition(",")
    if not sep:
        return "image/png", data_url
    mime_type = "image/png"
    if prefix.startswith("data:"):
        mime_type = prefix[5:].split(";", 1)[0] or mime_type
    return mime_type, encoded


def _build_reference_image_variables(reference_images: list[str]) -> dict[str, object]:
    variables: dict[str, object] = {
        "reference_images": [],
        "reference_image_count": 0,
    }
    normalized_refs: list[str] = []
    for index, image_url in enumerate(reference_images, start=1):
        cleaned_url = (image_url or "").strip()
        if not cleaned_url:
            continue
        data_url = load_image_as_data_url(cleaned_url)
        mime_type, encoded = _parse_data_url_parts(data_url)
        inline_part = {
            "inlineData": {
                "mimeType": mime_type,
                "data": encoded,
            }
        }
        normalized_refs.append(cleaned_url)
        variables[f"reference_image_{index}"] = inline_part
        variables[f"reference_image_{index}_url"] = cleaned_url
        variables[f"reference_image_{index}_data_url"] = data_url
        variables[f"reference_image_{index}_base64"] = encoded
        variables[f"reference_image_{index}_mime_type"] = mime_type
    variables["reference_images"] = normalized_refs
    variables["reference_image_count"] = len(normalized_refs)
    return variables


def optimize_prompt(
    db: Session,
    user_id: int,
    prompt: str,
    reference_images: list[str] | None = None,
    *,
    style_name: str,
    style_prompt: str,
    source: str = "web",
) -> str:
    normalized_prompt = (prompt or "").strip()
    if not normalized_prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="提示词不能为空")
    normalized_style_name = (style_name or "").strip()
    normalized_style_prompt = (style_prompt or "").strip()
    if not normalized_style_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="提示词风格名称不能为空")
    if not normalized_style_prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="提示词风格内容不能为空")

    api_config = require_scene_config(db, SCENE_PROMPT_OPTIMIZE)
    credit_cost = get_scene_credit_cost(db, SCENE_PROMPT_OPTIMIZE)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户不存在")

    current_balance = get_user_credit_balance(db, user.id)
    if not _is_credit_exempt_user(user) and current_balance < credit_cost:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"积分不足，需要 {credit_cost} 积分，当前余额 {current_balance}",
        )

    normalized_refs = [str(item or "").strip() for item in (reference_images or []) if str(item or "").strip()]
    render_variables = {
        **build_secret_variables(db),
        **_build_reference_image_variables(normalized_refs),
        "prompt": normalized_prompt,
        "prompt_optimize_text": PROMPT_OPTIMIZE_TEXT,
        "prompt_optimize_style_prompt": normalized_style_prompt,
        "style_prompt": normalized_style_prompt,
    }
    rendered = render_config(api_config, render_variables)

    try:
        with httpx.Client(timeout=settings.AI_TIMEOUT, trust_env=False) as client:
            response = client.post(rendered.request_url, **build_external_request_kwargs(rendered))
        if response.status_code != 200:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"提示词优化失败：{detail}",
            )
        optimized_prompt = _extract_prompt_text(response.json())
    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="提示词优化请求超时，请稍后重试")
    except Exception:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="提示词优化服务异常，请稍后重试")

    if not _is_credit_exempt_user(user):
        credit_description = PROMPT_OPTIMIZE_CREDIT_LOG_DESCRIPTION
        if (source or "").strip().lower() == "api":
            credit_description = f"API {credit_description}"
        change_user_credit_balance(
            db,
            user_id,
            delta=-credit_cost,
            log_type="consume",
            description=credit_description,
        )

    db.add(PromptOptimizeTask(
        user_id=user_id,
        style_id=None,
        style_name_snapshot=normalized_style_name,
        source=(source or "").strip().lower() or "web",
        original_prompt=normalized_prompt,
        optimized_prompt=optimized_prompt,
        reference_images_json=json.dumps(normalized_refs, ensure_ascii=False),
        source_image=normalized_refs[0] if normalized_refs else "",
        status="success",
        credit_cost=int(credit_cost or 0),
    ))
    db.commit()
    return optimized_prompt
