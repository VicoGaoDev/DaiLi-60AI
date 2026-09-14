#!/usr/bin/env python3
"""Measure one configurable generation API call without mutating task state."""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.models.external_api_config import ExternalApiConfig
from app.models.task import Task
from app.models.task_api_attempt import TaskApiAttempt
from app.services.cos_service import load_image_bytes
from app.services.external_api_config_service import (
    SCENE_INPAINT,
    SCENE_SMART_CUTOUT,
    build_external_request_kwargs,
    build_secret_variables,
    read_value_by_path,
    render_config,
    resolve_mapped_resolution,
    resolve_smart_cutout_prompt,
    should_use_multipart_request,
)
from app.services.image_delivery_service import get_optional_cos_config, serialize_asset_urls


DEFAULT_BUSINESS_ID = "df8877c23fcf48a8810506c5bde9e46c"


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def _parse_reference_images(task: Task) -> list[str]:
    if not task.reference_images:
        return []
    try:
        refs = json.loads(task.reference_images)
    except (json.JSONDecodeError, TypeError):
        return []
    return refs if isinstance(refs, list) else []


def _resolve_task_mode_and_scene_key(task: Task) -> tuple[str, str]:
    task_mode = (task.mode or "generate").lower()
    if task_mode == "inpaint":
        return task_mode, SCENE_INPAINT
    if task_mode == "smart_cutout":
        return task_mode, SCENE_SMART_CUTOUT
    return task_mode, task.model or ""


def _build_reference_image_payload(image_url: str) -> dict[str, object] | None:
    result = load_image_bytes(image_url)
    if not result:
        return None
    data, mime_type = result
    b64_data = base64.b64encode(data).decode("utf-8")
    return {
        "inline_part": {"inlineData": {"mimeType": mime_type, "data": b64_data}},
        "base64": b64_data,
        "mime_type": mime_type,
        "data_url": f"data:{mime_type};base64,{b64_data}",
    }


def _apply_smart_cutout_rendered_payload(payload: object, prompt: str) -> object:
    if not isinstance(payload, dict):
        return payload
    next_payload = dict(payload)
    next_payload["prompt"] = prompt
    if isinstance(next_payload.get("size"), str) and not next_payload["size"].strip():
        next_payload.pop("size", None)
    return next_payload


def _extract_configured_image_data(
    payload: dict,
    field_path: str,
) -> tuple[tuple[bytes, str] | None, str]:
    image_b64, parent = read_value_by_path(payload, field_path)
    if isinstance(image_b64, str) and image_b64.strip():
        mime_type = "image/png"
        if isinstance(parent, dict):
            mime_type = str(parent.get("mimeType") or parent.get("mime_type") or mime_type)
        try:
            return (base64.b64decode(image_b64), mime_type), ""
        except Exception as exc:
            return None, f"base64 decode failed: {exc}"

    candidate_paths: list[str] = []
    if isinstance(parent, dict):
        candidate_paths.append(f"{field_path.rsplit('.', 1)[0]}.url" if "." in field_path else "url")
    candidate_paths.append("data.0.url")
    for candidate_path in dict.fromkeys(candidate_paths):
        image_url, _ = read_value_by_path(payload, candidate_path)
        if not isinstance(image_url, str) or not image_url.strip():
            continue
        result = load_image_bytes(image_url.strip())
        if result:
            return result, ""
        return None, f"image url download failed: {candidate_path}"

    return None, f"missing configured field and fallback url: {field_path}"


def _connect_database(db_name: str | None):
    url = make_url(settings.database_url)
    if db_name:
        url = url.set(database=db_name)
    engine = create_engine(url, pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _latest_attempt_config_id(db, task_id: int) -> int | None:
    attempt = (
        db.query(TaskApiAttempt)
        .filter(TaskApiAttempt.task_id == task_id, TaskApiAttempt.api_config_id.is_not(None))
        .order_by(TaskApiAttempt.id.desc())
        .first()
    )
    return int(attempt.api_config_id) if attempt and attempt.api_config_id else None


def _build_render_variables(db, task: Task, ref_urls: list[str]) -> tuple[dict[str, Any], float]:
    started_at = time.perf_counter()
    task_mode, scene_key = _resolve_task_mode_and_scene_key(task)
    mapped_resolution = resolve_mapped_resolution(
        db,
        scene_key,
        task.size or "",
        task.resolution or "",
    )
    cos_config = get_optional_cos_config(db)
    variables: dict[str, Any] = {
        **build_secret_variables(db),
        "prompt": task.prompt or "",
        "aspect_ratio": task.size or "",
        "image_size": task.resolution or "",
        "custom_size": task.custom_size or "",
        "mapped_resolution": mapped_resolution,
        "generation_config": {},
        "mode": task_mode,
        "reference_image_count": 0,
    }

    parts: list[dict[str, Any]] = []
    reference_count = 0
    for index, ref_url in enumerate(ref_urls, start=1):
        reference_payload = _build_reference_image_payload(ref_url)
        if not reference_payload:
            print(f"warn: reference image {index} could not be loaded: {ref_url}")
            continue
        inline_part = reference_payload.get("inline_part")
        if isinstance(inline_part, dict):
            parts.append(inline_part)
        reference_count += 1
        variables[f"reference_image_{index}"] = inline_part
        variables[f"reference_image_{index}_url"] = serialize_asset_urls(ref_url, cos_config=cos_config)["image_url"]
        variables[f"reference_image_{index}_base64"] = reference_payload["base64"]
        variables[f"reference_image_{index}_mime_type"] = reference_payload["mime_type"]
        variables[f"reference_image_{index}_data_url"] = reference_payload["data_url"]

    variables["reference_image_count"] = reference_count
    if task_mode == "smart_cutout":
        prompt = resolve_smart_cutout_prompt(task.prompt or "", reference_count)
        variables["prompt"] = prompt
        parts.append({"text": prompt})
    else:
        parts.append({"text": task.prompt or ""})

    generation_config: dict[str, Any] = {"responseModalities": ["IMAGE"]}
    if task_mode != "inpaint":
        generation_config["imageConfig"] = {"aspectRatio": task.size or ""}
        if task.resolution:
            generation_config["imageConfig"]["imageSize"] = task.resolution
    variables["contents_parts"] = parts
    variables["generation_config"] = generation_config
    return variables, _elapsed_ms(started_at)


def _summarize_response(payload: Any, field_path: str) -> dict[str, Any]:
    configured_value, parent = read_value_by_path(payload, field_path)
    url_value, _ = read_value_by_path(payload, "data.0.url")
    return {
        "top_level_keys": list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__,
        "configured_field": field_path,
        "configured_field_present": isinstance(configured_value, str) and bool(configured_value.strip()),
        "configured_field_type": type(configured_value).__name__,
        "sibling_keys": list(parent.keys()) if isinstance(parent, dict) else type(parent).__name__,
        "data_0_url_present": isinstance(url_value, str) and bool(url_value.strip()),
        "data_0_url_prefix": url_value[:120] if isinstance(url_value, str) else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure a single configured generation API call.")
    parser.add_argument("--business-id", default=DEFAULT_BUSINESS_ID)
    parser.add_argument("--db-name", default="80ai")
    parser.add_argument("--api-config-id", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=float(settings.AI_TIMEOUT))
    parser.add_argument("--output", default="", help="Optional path to save returned image bytes.")
    args = parser.parse_args()

    Session = _connect_database(args.db_name)
    with Session() as db:
        task = db.query(Task).filter(Task.business_id == args.business_id).first()
        if not task:
            raise SystemExit(f"task not found: {args.business_id}")

        config_id = args.api_config_id or _latest_attempt_config_id(db, task.id) or task.provider_api_config_id
        if not config_id:
            raise SystemExit("api config id not found; pass --api-config-id explicitly")
        config = db.query(ExternalApiConfig).filter(ExternalApiConfig.id == config_id).first()
        if not config:
            raise SystemExit(f"api config not found: {config_id}")

        task_mode, scene_key = _resolve_task_mode_and_scene_key(task)
        ref_urls = _parse_reference_images(task)
        print(f"db={args.db_name}")
        print(f"task={task.business_id} internal_id={task.id} mode={task_mode} scene={scene_key}")
        print(f"api_config={config.id} {config.name} call_mode={config.call_mode} request_format={config.request_format}")
        print(f"request_url={config.request_url}")
        print(f"result_base64_field={config.result_base64_field or '(empty)'}")
        print(f"reference_image_count={len(ref_urls)}")

        variables, prepare_variables_ms = _build_render_variables(db, task, ref_urls)
        rendered = render_config(config, variables)
        if task_mode == "smart_cutout":
            rendered.payload = _apply_smart_cutout_rendered_payload(
                rendered.payload,
                str(variables.get("prompt") or resolve_smart_cutout_prompt(task.prompt or "", int(variables.get("reference_image_count") or 0))),
            )

        started_at = time.perf_counter()
        request_kwargs = build_external_request_kwargs(rendered)
        build_request_ms = _elapsed_ms(started_at)
        print(f"prepare_variables_ms={prepare_variables_ms}")
        print(f"build_request_kwargs_ms={build_request_ms}")
        print(f"request_mode={'multipart' if should_use_multipart_request(rendered) else 'json'}")

        started_at = time.perf_counter()
        with httpx.Client(timeout=args.timeout, trust_env=False) as client:
            response = client.post(rendered.request_url, **request_kwargs)
        http_ms = _elapsed_ms(started_at)
        print(f"http_status={response.status_code}")
        print(f"http_elapsed_ms={http_ms}")
        print(f"response_bytes={len(response.content)}")

        started_at = time.perf_counter()
        payload = response.json()
        json_parse_ms = _elapsed_ms(started_at)
        print(f"json_parse_ms={json_parse_ms}")
        print("response_summary=" + json.dumps(_summarize_response(payload, config.result_base64_field or ""), ensure_ascii=False))

        started_at = time.perf_counter()
        result, error_message = _extract_configured_image_data(payload, config.result_base64_field or "")
        extract_result_ms = _elapsed_ms(started_at)
        print(f"extract_result_ms={extract_result_ms}")
        if result:
            image_bytes, mime_type = result
            print(f"result=success mime={mime_type} image_bytes={len(image_bytes)}")
            if args.output:
                output_path = Path(args.output)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(image_bytes)
                print(f"saved_result={output_path}")
        else:
            print(f"result=failed error={error_message}")
            print("response_preview=" + response.text[:1000])
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
