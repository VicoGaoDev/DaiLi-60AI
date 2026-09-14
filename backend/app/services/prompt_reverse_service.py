import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models.credit_log import CreditLog
from app.models.prompt_history import PromptHistory
from app.models.user import User
from app.services.user_credit_service import change_user_credit_balance, get_user_credit_balance
from app.services.cos_service import load_image_as_data_url
from app.services.external_api_config_service import (
    build_external_request_kwargs,
    build_secret_variables,
    get_scene_credit_cost,
    render_config,
    require_scene_config,
    SCENE_PROMPT_REVERSE,
)
PROMPT_REVERSE_MODE = "promptReverse"
PROMPT_REVERSE_MODEL = "提示词反推"
PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION = "提示词反推"

PROMPT_REVERSE_TEXT = (
    "你是 AI 绘画提示词反推助手。目标不是描述这张图，而是写出一段能让图像生成模型复刻出相近画面的中文提示词。"
    "风格、媒介、笔触和画面气质的还原，优先于主体零件罗列。"
    "\n\n先根据画面证据判断媒介，只能选最贴近的一类："
    "摄影、电影剧照、3D渲染、插画、动漫、水彩、油画、厚涂、矢量平面、涂鸦速写、线稿草稿、设计海报。"
    "再写清线条气质（严谨精细、干净矢量、随性速写、杂乱涂鸦、粗犷干笔、未完成草稿），"
    "上色方式（平涂、干笔块面、飞白、叠压、厚涂、晕染、渐变、留白），"
    "以及背景处理（大面积留白、简洁色块、复杂场景、虚化环境）。"
    "若画面里有签名、手写字、箭头、圆圈、标记、重复线条等涂鸦或设计元素，必须写进提示词。"
    "\n\n严禁："
    "把插画、涂鸦、速写误写成摄影术语，例如低角度拍摄、高清晰度、光影细腻，除非画面本身就是照片；"
    "使用空泛夸夸词，例如高清晰度、细节丰富、质感细腻、色彩饱满、时尚感十足，这类词会把草稿风画成精修图；"
    "编造看不到的品牌、型号、精确参数或配置；能识别的主体可以写，但不要补全图中没有的细节；"
    "输出分析报告、标题、分点，或“主体/风格/构图/光影/色彩/画质/细节”这类小标题。"
    "\n\n只输出一段可直接生图的中文提示词，用中文逗号连接，不要解释。"
    "顺序：画风与媒介，主体与姿态，构图与留白，线条与笔触，色彩与上色方式，文字签名与符号，需要规避的相反风格。"
    "如果画面明显是涂鸦、速写、草稿、手绘，必须写明涂鸦速写、即兴手绘、草稿质感，"
    "并加上对应禁止项，例如不要写实精修、不要细腻水彩晕染、不要复杂真实背景。"
)


def _is_credit_exempt_user(user: User | None) -> bool:
    return bool(user and user.role == "superadmin")
def _extract_prompt_text(payload: dict) -> str:
    candidate_paths = [
        payload.get("text"),
        payload.get("choices", [{}])[0].get("message", {}).get("content"),
        payload.get("choices", [{}])[0].get("message", {}).get("content", [{}]),
        payload.get("choices", [{}])[0].get("message", {}).get("text"),
        payload.get("choices", [{}])[0].get("text"),
        payload.get("output", {}).get("text"),
        payload.get("output", {}).get("choices", [{}])[0].get("message", {}).get("content"),
        payload.get("output", {}).get("choices", [{}])[0].get("message", {}).get("content", [{}]),
        payload.get("output", {}).get("choices", [{}])[0].get("message", {}).get("text"),
    ]

    for candidate in candidate_paths:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
        if isinstance(candidate, list):
            text_parts: list[str] = []
            for item in candidate:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    text_parts.append(item["text"].strip())
                elif isinstance(item, str):
                    text_parts.append(item.strip())
            joined = "\n".join(part for part in text_parts if part)
            if joined:
                return joined

    raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="提示词反推返回内容为空")


def reverse_prompt_from_image(db: Session, user_id: int, image_url: str, *, source: str = "web") -> str:
    api_config = require_scene_config(db, SCENE_PROMPT_REVERSE)
    credit_cost = get_scene_credit_cost(db, SCENE_PROMPT_REVERSE)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户不存在",
        )
    current_balance = get_user_credit_balance(db, user.id)
    if not _is_credit_exempt_user(user) and current_balance < credit_cost:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"积分不足，需要 {credit_cost} 积分，当前余额 {current_balance}",
        )

    image_data_url = load_image_as_data_url(image_url)
    rendered = render_config(
        api_config,
        {
            **build_secret_variables(db),
            "image_data_url": image_data_url,
            "prompt_reverse_text": PROMPT_REVERSE_TEXT,
        },
    )

    try:
        with httpx.Client(timeout=settings.AI_TIMEOUT, trust_env=False) as client:
            response = client.post(
                rendered.request_url,
                **build_external_request_kwargs(rendered),
            )
        if response.status_code != 200:
            try:
                detail = response.json()
            except Exception:
                detail = response.text
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"提示词反推失败：{detail}",
            )
        prompt = _extract_prompt_text(response.json())
    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="提示词反推请求超时，请稍后重试")
    except Exception:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="提示词反推服务异常，请稍后重试")

    if not _is_credit_exempt_user(user):
        credit_description = PROMPT_REVERSE_CREDIT_LOG_DESCRIPTION
        if (source or "").strip().lower() == "api":
            credit_description = f"API {credit_description}"
        change_user_credit_balance(
            db,
            user_id,
            delta=-credit_cost,
            log_type="consume",
            description=credit_description,
        )
    db.add(PromptHistory(
        user_id=user_id,
        prompt=prompt,
        mode=PROMPT_REVERSE_MODE,
        source_image=image_url.strip(),
    ))
    db.commit()
    return prompt
