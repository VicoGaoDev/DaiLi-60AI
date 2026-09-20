from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.wecom_notify_rule import WecomNotifyRule
from app.models.wecom_webhook_channel import WecomWebhookChannel
from app.utils.business_id import generate_business_id
from app.utils.datetime_utils import now_local


logger = logging.getLogger(__name__)
TEMPLATE_VARIABLE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

EVENT_PAYMENT_SUCCESS = "payment_success"
EVENT_REDEEM_SUCCESS = "redeem_success"
EVENT_OFFLINE_ORDER = "offline_order"
EVENT_USER_REGISTERED = "user_registered"
EVENT_FEEDBACK_CREATED = "feedback_created"
EVENT_FEEDBACK_REPLIED = "feedback_replied"
EVENT_REFERRAL_REWARD = "referral_reward"
EVENT_PROMO_REWARD = "promo_reward"
EVENT_ADMIN_USER_ACTION = "admin_user_action"
EVENT_DAILY_REPORT = "daily_report"
EVENT_API_ALERT = "api_alert"

BUSINESS_SEED_EVENTS = (
    EVENT_PAYMENT_SUCCESS,
    EVENT_REDEEM_SUCCESS,
    EVENT_FEEDBACK_CREATED,
    EVENT_FEEDBACK_REPLIED,
    EVENT_REFERRAL_REWARD,
    EVENT_PROMO_REWARD,
    EVENT_ADMIN_USER_ACTION,
    EVENT_DAILY_REPORT,
)

EVENT_CATALOG: list[dict[str, Any]] = [
    {
        "event_key": EVENT_PAYMENT_SUCCESS,
        "label": "订单购买成功",
        "fields": [
            {"key": "min_amount_yuan", "label": "最低金额（元）", "type": "number", "optional": True},
        ],
    },
    {
        "event_key": EVENT_REDEEM_SUCCESS,
        "label": "兑换码兑换成功",
        "fields": [
            {"key": "include_gift", "label": "包含赠送兑换", "type": "boolean", "optional": True, "default": True},
        ],
    },
    {
        "event_key": EVENT_OFFLINE_ORDER,
        "label": "线下订单录入",
        "fields": [
            {
                "key": "order_types",
                "label": "订单类型",
                "type": "multi_select",
                "optional": True,
                "options": [
                    {"value": "purchase", "label": "购买"},
                    {"value": "refund", "label": "退款"},
                ],
            },
        ],
    },
    {"event_key": EVENT_USER_REGISTERED, "label": "新用户注册", "fields": []},
    {"event_key": EVENT_FEEDBACK_CREATED, "label": "用户提交新反馈", "fields": []},
    {"event_key": EVENT_FEEDBACK_REPLIED, "label": "用户追加反馈", "fields": []},
    {"event_key": EVENT_REFERRAL_REWARD, "label": "邀请奖励已发放", "fields": []},
    {"event_key": EVENT_PROMO_REWARD, "label": "推广现金返利已记账", "fields": []},
    {"event_key": EVENT_ADMIN_USER_ACTION, "label": "用户管理操作", "fields": []},
    {"event_key": EVENT_DAILY_REPORT, "label": "周期经营日报", "fields": []},
    {"event_key": EVENT_API_ALERT, "label": "接口质量告警", "fields": []},
]

EVENT_LABELS = {item["event_key"]: item["label"] for item in EVENT_CATALOG}

EVENT_VARIABLES: dict[str, list[dict[str, Any]]] = {
    EVENT_PAYMENT_SUCCESS: [
        {"key": "order_no", "label": "订单号", "example": "P202609170001"},
        {"key": "user_label", "label": "用户", "example": "administrator"},
        {"key": "subject", "label": "套餐", "example": "100 积分套餐"},
        {"key": "amount_yuan", "label": "金额（元）", "example": "100.00"},
        {"key": "credits", "label": "到账积分", "example": "100"},
        {"key": "used_credit", "label": "已使用积分", "example": "20"},
        {"key": "remain_credit", "label": "剩余积分", "example": "80"},
        {"key": "time", "label": "时间", "example": "2026-09-17 17:00:00"},
    ],
    EVENT_REDEEM_SUCCESS: [
        {"key": "user_label", "label": "用户", "example": "administrator"},
        {"key": "redeem_key", "label": "兑换码", "example": "ABCD1234EFGH5678"},
        {"key": "gift_title", "label": "赠送标题后缀", "example": "（赠送）"},
        {"key": "gift_line", "label": "赠送类型行", "example": "> 🏷️ 类型: **赠送**\n"},
        {"key": "gift_label", "label": "兑换类型", "example": "赠送"},
        {"key": "credit_amount", "label": "兑换积分", "example": "100"},
        {"key": "used_credit", "label": "已使用积分", "example": "20"},
        {"key": "remain_credit", "label": "剩余积分", "example": "80"},
        {"key": "time", "label": "兑换时间", "example": "2026-09-17 17:00:00"},
    ],
    EVENT_OFFLINE_ORDER: [
        {"key": "user_label", "label": "用户", "example": "administrator"},
        {"key": "order_type", "label": "订单类型值", "example": "purchase"},
        {"key": "order_type_label", "label": "订单类型", "example": "购买"},
        {"key": "amount_yuan", "label": "金额（元）", "example": "100.00"},
        {"key": "credit_amount", "label": "积分", "example": "100"},
        {"key": "remark", "label": "备注", "example": "线下转账"},
        {"key": "admin_label", "label": "操作人", "example": "administrator"},
        {"key": "time", "label": "时间", "example": "2026-09-17 17:00:00"},
    ],
    EVENT_USER_REGISTERED: [
        {"key": "user_label", "label": "用户", "example": "new-user"},
        {"key": "register_method", "label": "注册方式", "example": "邮箱"},
        {"key": "has_invite", "label": "是否有邀请", "example": "否"},
        {"key": "time", "label": "时间", "example": "2026-09-17 17:00:00"},
    ],
    EVENT_FEEDBACK_CREATED: [
        {"key": "feedback_id", "label": "反馈单号", "example": "fb_001"},
        {"key": "feedback_type", "label": "反馈类型", "example": "通用反馈"},
        {"key": "user_label", "label": "用户", "example": "administrator"},
        {"key": "used_credit", "label": "已使用积分", "example": "20"},
        {"key": "remain_credit", "label": "剩余积分", "example": "80"},
        {"key": "time", "label": "提交时间", "example": "2026-09-17 17:00:00"},
        {"key": "attachment_count", "label": "附件数量", "example": "1"},
        {"key": "content_preview", "label": "反馈内容", "example": "页面按钮不可点击"},
    ],
    EVENT_FEEDBACK_REPLIED: [
        {"key": "feedback_id", "label": "反馈单号", "example": "fb_001"},
        {"key": "user_label", "label": "用户", "example": "administrator"},
        {"key": "time", "label": "发送时间", "example": "2026-09-17 17:00:00"},
        {"key": "attachment_count", "label": "图片数量", "example": "1"},
        {"key": "content_preview", "label": "消息内容", "example": "补充一张截图"},
    ],
    EVENT_REFERRAL_REWARD: [
        {"key": "referrer_label", "label": "邀请人", "example": "user-a"},
        {"key": "invitee_label", "label": "被邀请用户", "example": "user-b"},
        {"key": "source_type_label", "label": "奖励来源", "example": "在线购买"},
        {"key": "source_id", "label": "来源编号", "example": "P202609170001"},
        {"key": "source_credits", "label": "对方到账积分", "example": "100"},
        {"key": "reward_rate", "label": "奖励比例", "example": "15"},
        {"key": "reward_credits", "label": "发放奖励积分", "example": "15"},
        {"key": "reward_index", "label": "第几次奖励", "example": "1"},
        {"key": "used_credit", "label": "邀请人已使用积分", "example": "20"},
        {"key": "remain_credit", "label": "邀请人剩余积分", "example": "80"},
        {"key": "time", "label": "发放时间", "example": "2026-09-17 17:00:00"},
    ],
    EVENT_PROMO_REWARD: [
        {"key": "referrer_label", "label": "推广人", "example": "user-a"},
        {"key": "invitee_label", "label": "被推广用户", "example": "user-b"},
        {"key": "source_id", "label": "订单号", "example": "P202609170001"},
        {"key": "source_amount_yuan", "label": "订单金额", "example": "100.00"},
        {"key": "reward_rate", "label": "返利比例", "example": "40"},
        {"key": "reward_amount_yuan", "label": "记账返利", "example": "40.00"},
        {"key": "reward_index", "label": "第几次返利", "example": "1"},
        {"key": "time", "label": "记账时间", "example": "2026-09-17 17:00:00"},
    ],
    EVENT_ADMIN_USER_ACTION: [
        {"key": "operator_label", "label": "操作人", "example": "administrator"},
        {"key": "target_user_label", "label": "操作对象", "example": "user-a"},
        {"key": "target_user_id", "label": "用户 ID", "example": "9ce3727ca9984d7091d504ae2055a714"},
        {"key": "action_type", "label": "操作类型", "example": "启用用户"},
        {"key": "details", "label": "操作详情", "example": "> 状态: 禁用 → 启用\n"},
        {"key": "time", "label": "操作时间", "example": "2026-09-17 17:00:00"},
    ],
    EVENT_DAILY_REPORT: [
        {"key": "report_markdown", "label": "日报完整内容", "example": "## 📊 周期经营数据报告\n> 📅 周期: **2026-09-17**"},
    ],
    EVENT_API_ALERT: [
        {"key": "alert_markdown", "label": "告警完整内容", "example": "## 🚨 接口质量告警\n> 状态: **接口指标异常**"},
    ],
}

EVENT_DEFAULT_TEMPLATES: dict[str, str] = {
    EVENT_PAYMENT_SUCCESS: (
        "## 💰 订单购买成功\n"
        "> 🧾 订单号: `{{order_no}}`\n"
        "> 👤 用户: **{{user_label}}**\n"
        "> 📦 套餐: **{{subject}}**\n"
        "> 💵 金额: <font color=\"warning\">¥{{amount_yuan}}</font>\n"
        "> ⚡ 积分到账: **{{credits}}**\n"
        "> ⚡ 已使用积分: **{{used_credit}}**\n"
        "> ⚡ 剩余积分: **{{remain_credit}}**\n"
        "> ⏰ 时间: {{time}}"
    ),
    EVENT_REDEEM_SUCCESS: (
        "## 🎁 兑换码兑换成功{{gift_title}}\n"
        "> 👤 用户: **{{user_label}}**\n"
        "> 🔑 兑换码: `{{redeem_key}}`\n"
        "{{gift_line}}"
        "> ⚡ 兑换积分: **{{credit_amount}}**\n"
        "> ⚡ 已使用积分: **{{used_credit}}**\n"
        "> ⚡ 剩余积分: **{{remain_credit}}**\n"
        "> ⏰ 兑换时间: {{time}}"
    ),
    EVENT_OFFLINE_ORDER: (
        "## 🧾 线下订单已录入\n"
        "> 👤 用户: **{{user_label}}**\n"
        "> 🏷️ 类型: **{{order_type_label}}**\n"
        "> 💵 金额: <font color=\"warning\">¥{{amount_yuan}}</font>\n"
        "> ⚡ 积分: **{{credit_amount}}**\n"
        "> 📝 备注: {{remark}}\n"
        "> 🙋 操作人: **{{admin_label}}**\n"
        "> ⏰ 时间: {{time}}"
    ),
    EVENT_USER_REGISTERED: (
        "## 👤 新用户注册\n"
        "> 👤 用户: **{{user_label}}**\n"
        "> 🏷️ 方式: **{{register_method}}**\n"
        "> 🔗 邀请: **{{has_invite}}**\n"
        "> ⏰ 时间: {{time}}"
    ),
    EVENT_FEEDBACK_CREATED: (
        "## 💬 用户提交新反馈\n"
        "> 🧾 反馈单号: `{{feedback_id}}`\n"
        "> 🏷️ 类型: **{{feedback_type}}**\n"
        "> 👤 用户: **{{user_label}}**\n"
        "> ⚡ 已使用积分: **{{used_credit}}**\n"
        "> ⚡ 剩余积分: **{{remain_credit}}**\n"
        "> ⏰ 提交时间: {{time}}\n"
        "> 🖼️ 附件数量: **{{attachment_count}}**\n"
        "> 📝 反馈内容: {{content_preview}}"
    ),
    EVENT_FEEDBACK_REPLIED: (
        "## 用户追加反馈消息\n"
        "> 反馈单号: `{{feedback_id}}`\n"
        "> 用户: **{{user_label}}**\n"
        "> 发送时间: {{time}}\n"
        "> 图片数量: **{{attachment_count}}**\n"
        "> 消息内容: {{content_preview}}"
    ),
    EVENT_REFERRAL_REWARD: (
        "## 🎉 邀请奖励已发放\n"
        "> 👤 邀请人: **{{referrer_label}}**\n"
        "> 🙋 被邀请用户: **{{invitee_label}}**\n"
        "> 🏷️ 奖励来源: **{{source_type_label}}**\n"
        "> 🔖 来源编号: `{{source_id}}`\n"
        "> ⚡ 对方到账积分: **{{source_credits}}**\n"
        "> 🎁 奖励比例: **{{reward_rate}}%**\n"
        "> 🎁 发放奖励积分: **{{reward_credits}}**\n"
        "> 🔁 第 **{{reward_index}}** 次奖励\n"
        "> ⚡ 邀请人已使用积分: **{{used_credit}}**\n"
        "> ⚡ 邀请人剩余积分: **{{remain_credit}}**\n"
        "> ⏰ 发放时间: {{time}}"
    ),
    EVENT_PROMO_REWARD: (
        "## 💰 推广现金返利已记账\n"
        "> 👤 推广人: **{{referrer_label}}**\n"
        "> 🙋 被推广用户: **{{invitee_label}}**\n"
        "> 🔖 订单号: `{{source_id}}`\n"
        "> 💵 订单金额: **¥{{source_amount_yuan}}**\n"
        "> 🎁 返利比例: **{{reward_rate}}%**\n"
        "> 🎁 记账返利: **¥{{reward_amount_yuan}}**\n"
        "> 🔁 第 **{{reward_index}}** 次返利\n"
        "> ⏰ 记账时间: {{time}}\n"
        "> ℹ️ 仅统计金额，平台不支持提现"
    ),
    EVENT_ADMIN_USER_ACTION: (
        "## 👤 用户管理操作通知\n"
        "> 🙋 操作人: **{{operator_label}}**\n"
        "> 🎯 操作对象: **{{target_user_label}}**\n"
        "> 🧾 用户ID: `{{target_user_id}}`\n"
        "> 🛠️ 操作类型: **{{action_type}}**\n"
        "{{details}}"
        "> ⏰ 操作时间: {{time}}"
    ),
    EVENT_DAILY_REPORT: "{{report_markdown}}",
    EVENT_API_ALERT: "{{alert_markdown}}",
}


def get_wecom_event_catalog() -> list[dict[str, Any]]:
    return [
        {
            **item,
            "variables": EVENT_VARIABLES.get(item["event_key"], []),
            "default_template": EVENT_DEFAULT_TEMPLATES.get(item["event_key"], ""),
        }
        for item in EVENT_CATALOG
    ]


def get_default_template(event_key: str) -> str:
    return EVENT_DEFAULT_TEMPLATES.get(event_key, "")


def get_test_context(event_key: str) -> dict[str, Any]:
    sample = {item["key"]: item.get("example", "-") for item in EVENT_VARIABLES.get(event_key, [])}
    sample.setdefault("time", now_local().strftime("%Y-%m-%d %H:%M:%S"))
    return sample


def _allowed_template_variables(event_key: str) -> set[str]:
    return {item["key"] for item in EVENT_VARIABLES.get(event_key, [])}


def _template_variables(template_markdown: str) -> set[str]:
    return set(TEMPLATE_VARIABLE_RE.findall(template_markdown or ""))


def validate_template_markdown(event_key: str, template_markdown: str) -> str:
    normalized = (template_markdown or "").strip()
    if not normalized:
        return get_default_template(event_key)
    unknown = sorted(_template_variables(normalized) - _allowed_template_variables(event_key))
    if unknown:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"模版变量不支持: {', '.join(unknown)}")
    return normalized


def _format_template_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def render_wecom_template(template_markdown: str, context: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in context:
            logger.warning("Missing WeCom template variable: %s", key)
        return _format_template_value(context.get(key))

    return TEMPLATE_VARIABLE_RE.sub(replace, template_markdown or "")


def _parse_conditions(raw: str | None) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def dump_conditions(conditions: dict[str, Any] | None) -> str:
    return json.dumps(conditions or {}, ensure_ascii=False, separators=(",", ":"))


def match_conditions(conditions: dict[str, Any], context: dict[str, Any]) -> bool:
    if not conditions:
        return True

    if "min_amount_yuan" in conditions:
        try:
            minimum = float(conditions["min_amount_yuan"])
        except (TypeError, ValueError):
            return False
        try:
            amount = float(context.get("amount_yuan") or 0)
        except (TypeError, ValueError):
            return False
        if amount < minimum:
            return False

    if "include_gift" in conditions:
        include_gift = bool(conditions["include_gift"])
        if not include_gift and bool(context.get("is_gift")):
            return False

    if "order_types" in conditions:
        allowed = conditions["order_types"]
        if not isinstance(allowed, list) or not allowed:
            return False
        order_type = str(context.get("order_type") or "")
        if order_type not in {str(item) for item in allowed}:
            return False

    return True


def _event_fallback_is_alert(event_key: str) -> bool:
    return event_key == EVENT_API_ALERT


def env_fallback_enabled(event_key: str) -> tuple[bool, str]:
    if _event_fallback_is_alert(event_key):
        return bool(settings.API_ALERT_ENABLED), (settings.WECOM_ALERT_WEBHOOK_URL or "").strip()
    return bool(settings.WECOM_NOTIFY_ENABLED), (settings.WECOM_WEBHOOK_URL or "").strip()


def _serialize_channel(row: WecomWebhookChannel, *, rule_count: int | None = None) -> dict:
    payload = {
        "id": row.business_id,
        "name": row.name or "",
        "webhook_url": row.webhook_url or "",
        "is_enabled": bool(row.is_enabled),
        "remark": row.remark or "",
        "updated_at": row.updated_at,
    }
    if rule_count is not None:
        payload["rule_count"] = rule_count
    return payload


def _serialize_rule(row: WecomNotifyRule) -> dict:
    channel = row.channel
    return {
        "id": row.business_id,
        "channel_id": channel.business_id if channel else "",
        "channel_name": channel.name if channel else "",
        "event_key": row.event_key,
        "event_label": EVENT_LABELS.get(row.event_key, row.event_key),
        "name": row.name or "",
        "is_enabled": bool(row.is_enabled),
        "conditions": _parse_conditions(row.conditions_json),
        "template_markdown": row.template_markdown or get_default_template(row.event_key),
        "updated_at": row.updated_at,
    }


def _get_channel_by_external_id(db: Session, channel_id: str) -> WecomWebhookChannel | None:
    return db.query(WecomWebhookChannel).filter(WecomWebhookChannel.business_id == channel_id).first()


def _get_rule_by_external_id(db: Session, rule_id: str) -> WecomNotifyRule | None:
    return db.query(WecomNotifyRule).filter(WecomNotifyRule.business_id == rule_id).first()


def _normalize_webhook_url(webhook_url: str) -> str:
    normalized = (webhook_url or "").strip()
    if normalized and not normalized.startswith("https://"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Webhook 地址必须以 https:// 开头")
    return normalized


def seed_default_wecom_notify(db: Session) -> None:
    existing_channels = db.query(WecomWebhookChannel.id).first()
    existing_rules = db.query(WecomNotifyRule.id).first()
    if existing_channels is not None or existing_rules is not None:
        return

    business = WecomWebhookChannel(
        business_id=generate_business_id(),
        name="经营通知",
        webhook_url=(settings.WECOM_WEBHOOK_URL or "").strip(),
        is_enabled=bool(settings.WECOM_NOTIFY_ENABLED),
        remark="购买、兑换、反馈、日报等经营消息",
    )
    alert = WecomWebhookChannel(
        business_id=generate_business_id(),
        name="接口告警",
        webhook_url=(settings.WECOM_ALERT_WEBHOOK_URL or "").strip(),
        is_enabled=bool(settings.API_ALERT_ENABLED),
        remark="生图接口成功率、耗时等质量告警",
    )
    db.add(business)
    db.add(alert)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return

    for event_key in BUSINESS_SEED_EVENTS:
        db.add(
            WecomNotifyRule(
                business_id=generate_business_id(),
                channel_id=business.id,
                event_key=event_key,
                name=EVENT_LABELS.get(event_key, event_key),
                is_enabled=True,
                conditions_json="{}",
                template_markdown=get_default_template(event_key),
            )
        )
    db.add(
        WecomNotifyRule(
            business_id=generate_business_id(),
            channel_id=alert.id,
            event_key=EVENT_API_ALERT,
            name=EVENT_LABELS[EVENT_API_ALERT],
            is_enabled=True,
            conditions_json="{}",
            template_markdown=get_default_template(EVENT_API_ALERT),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def _has_any_rule(db: Session) -> bool:
    return db.query(WecomNotifyRule.id).first() is not None


def _has_any_channel(db: Session) -> bool:
    return db.query(WecomWebhookChannel.id).first() is not None


def backfill_missing_rule_templates(db: Session) -> None:
    rows = db.query(WecomNotifyRule).filter(WecomNotifyRule.template_markdown.is_(None)).all()
    if not rows:
        return
    for row in rows:
        row.template_markdown = get_default_template(row.event_key)
    db.commit()


def _enabled_rule_targets(db: Session, event_key: str, context: dict[str, Any]) -> list[dict[str, str]]:
    rows = (
        db.query(WecomNotifyRule)
        .join(WecomWebhookChannel, WecomWebhookChannel.id == WecomNotifyRule.channel_id)
        .filter(
            WecomNotifyRule.event_key == event_key,
            WecomNotifyRule.is_enabled.is_(True),
            WecomWebhookChannel.is_enabled.is_(True),
        )
        .all()
    )
    targets: list[dict[str, str]] = []
    for row in rows:
        if not match_conditions(_parse_conditions(row.conditions_json), context):
            continue
        url = (row.channel.webhook_url if row.channel else "") or ""
        url = url.strip()
        if not url:
            continue
        targets.append(
            {
                "rule_id": row.business_id,
                "webhook_url": url,
                "template_markdown": row.template_markdown or get_default_template(row.event_key),
            }
        )
    return targets


def _enabled_targets(db: Session, event_key: str, context: dict[str, Any]) -> list[str]:
    return [target["webhook_url"] for target in _enabled_rule_targets(db, event_key, context)]


def resolve_dispatch_targets(event_key: str, context: dict[str, Any] | None = None) -> list[dict[str, str]]:
    from app.database import SessionLocal

    payload = context or {}
    db = SessionLocal()
    try:
        has_rule = _has_any_rule(db)
        has_channel = _has_any_channel(db)
        if not has_rule and not has_channel:
            seed_default_wecom_notify(db)
        if not _has_any_rule(db):
            if _has_any_channel(db):
                return []
            enabled, url = env_fallback_enabled(event_key)
            return [{"webhook_url": url, "template_markdown": "", "rule_id": ""}] if enabled and url else []
        return _enabled_rule_targets(db, event_key, payload)
    except (ProgrammingError, OperationalError):
        db.rollback()
        enabled, url = env_fallback_enabled(event_key)
        return [{"webhook_url": url, "template_markdown": "", "rule_id": ""}] if enabled and url else []
    finally:
        db.close()


def resolve_dispatch_urls(event_key: str, context: dict[str, Any] | None = None) -> list[str]:
    return [target["webhook_url"] for target in resolve_dispatch_targets(event_key, context)]


def event_channel_enabled(event_key: str) -> bool:
    return bool(resolve_dispatch_urls(event_key, {}))


def list_wecom_channels(db: Session) -> list[dict]:
    seed_default_wecom_notify(db)
    rows = db.query(WecomWebhookChannel).order_by(WecomWebhookChannel.id.asc()).all()
    counts = {row.id: len(row.rules or []) for row in rows}
    return [_serialize_channel(row, rule_count=counts.get(row.id, 0)) for row in rows]


def create_wecom_channel(
    db: Session,
    *,
    name: str,
    webhook_url: str,
    is_enabled: bool = False,
    remark: str = "",
) -> dict:
    seed_default_wecom_notify(db)
    normalized_name = name.strip()
    if not normalized_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="通道名称不能为空")
    row = WecomWebhookChannel(
        business_id=generate_business_id(),
        name=normalized_name[:50],
        webhook_url=_normalize_webhook_url(webhook_url)[:500],
        is_enabled=bool(is_enabled),
        remark=(remark or "").strip()[:200],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_channel(row, rule_count=0)


def update_wecom_channel(
    db: Session,
    channel_id: str,
    *,
    name: str | None = None,
    webhook_url: str | None = None,
    is_enabled: bool | None = None,
    remark: str | None = None,
) -> dict:
    seed_default_wecom_notify(db)
    row = _get_channel_by_external_id(db, channel_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知通道不存在")
    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="通道名称不能为空")
        row.name = normalized_name[:50]
    if webhook_url is not None:
        row.webhook_url = _normalize_webhook_url(webhook_url)[:500]
    if is_enabled is not None:
        row.is_enabled = bool(is_enabled)
    if remark is not None:
        row.remark = remark.strip()[:200]
    db.commit()
    db.refresh(row)
    return _serialize_channel(row, rule_count=len(row.rules or []))


def delete_wecom_channel(db: Session, channel_id: str) -> None:
    seed_default_wecom_notify(db)
    row = _get_channel_by_external_id(db, channel_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知通道不存在")
    rule_count = db.query(WecomNotifyRule).filter(WecomNotifyRule.channel_id == row.id).count()
    if rule_count:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先删除该通道下的触发规则")
    db.delete(row)
    db.commit()


def test_wecom_channel(db: Session, channel_id: str) -> dict:
    from app.services.wecom_notify_service import send_wecom_markdown_to_url

    seed_default_wecom_notify(db)
    row = _get_channel_by_external_id(db, channel_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知通道不存在")
    webhook_url = (row.webhook_url or "").strip()
    if not webhook_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先填写 Webhook 地址")
    content = (
        f"## 企业微信通道测试\n"
        f"> 通道: **{row.name}**\n"
        f"> 当前开关: **{'开启' if row.is_enabled else '关闭'}**\n"
        f"> 时间: {now_local().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    sent = send_wecom_markdown_to_url(content, webhook_url)
    if not sent:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="测试消息发送失败，请检查 Webhook 地址")
    return {"sent": True, "channel_id": row.business_id}


def list_wecom_rules(db: Session) -> list[dict]:
    seed_default_wecom_notify(db)
    backfill_missing_rule_templates(db)
    rows = (
        db.query(WecomNotifyRule)
        .join(WecomWebhookChannel, WecomWebhookChannel.id == WecomNotifyRule.channel_id)
        .order_by(WecomNotifyRule.id.asc())
        .all()
    )
    return [_serialize_rule(row) for row in rows]


def _validate_event_key(event_key: str) -> str:
    normalized = (event_key or "").strip()
    if normalized not in EVENT_LABELS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的触发场景")
    return normalized


def _normalize_conditions(event_key: str, conditions: dict[str, Any] | None) -> dict[str, Any]:
    payload = conditions or {}
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="条件格式不正确")
    catalog = next((item for item in EVENT_CATALOG if item["event_key"] == event_key), None)
    allowed = {field["key"] for field in (catalog or {}).get("fields", [])}
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if key not in allowed or value is None or value == "":
            continue
        if key == "min_amount_yuan":
            try:
                amount = float(value)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="最低金额格式不正确") from exc
            if amount < 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="最低金额不能小于 0")
            cleaned[key] = amount
            continue
        if key == "include_gift":
            if not bool(value):
                cleaned[key] = False
            continue
        if key == "order_types":
            if not isinstance(value, list):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="订单类型格式不正确")
            types = [str(item) for item in value if str(item) in {"purchase", "refund"}]
            if types:
                cleaned[key] = types
            continue
    return cleaned


def create_wecom_rule(
    db: Session,
    *,
    channel_id: str,
    event_key: str,
    name: str = "",
    is_enabled: bool = True,
    conditions: dict[str, Any] | None = None,
    template_markdown: str | None = None,
) -> dict:
    seed_default_wecom_notify(db)
    channel = _get_channel_by_external_id(db, channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知通道不存在")
    normalized_event = _validate_event_key(event_key)
    normalized_name = (name or "").strip() or EVENT_LABELS[normalized_event]
    row = WecomNotifyRule(
        business_id=generate_business_id(),
        channel_id=channel.id,
        event_key=normalized_event,
        name=normalized_name[:80],
        is_enabled=bool(is_enabled),
        conditions_json=dump_conditions(_normalize_conditions(normalized_event, conditions)),
        template_markdown=validate_template_markdown(normalized_event, template_markdown or ""),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    row.channel = channel
    return _serialize_rule(row)


def update_wecom_rule(
    db: Session,
    rule_id: str,
    *,
    channel_id: str | None = None,
    event_key: str | None = None,
    name: str | None = None,
    is_enabled: bool | None = None,
    conditions: dict[str, Any] | None = None,
    template_markdown: str | None = None,
) -> dict:
    seed_default_wecom_notify(db)
    row = _get_rule_by_external_id(db, rule_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="触发规则不存在")
    event_changed = False
    if channel_id is not None:
        channel = _get_channel_by_external_id(db, channel_id)
        if channel is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知通道不存在")
        row.channel_id = channel.id
        row.channel = channel
    if event_key is not None:
        normalized_event = _validate_event_key(event_key)
        event_changed = normalized_event != row.event_key
        row.event_key = normalized_event
    if name is not None:
        normalized_name = name.strip() or EVENT_LABELS.get(row.event_key, row.event_key)
        row.name = normalized_name[:80]
    if is_enabled is not None:
        row.is_enabled = bool(is_enabled)
    if conditions is not None:
        row.conditions_json = dump_conditions(_normalize_conditions(row.event_key, conditions))
    elif event_changed:
        row.conditions_json = "{}"
    if template_markdown is not None:
        row.template_markdown = validate_template_markdown(row.event_key, template_markdown)
    elif event_changed:
        row.template_markdown = get_default_template(row.event_key)
    db.commit()
    db.refresh(row)
    return _serialize_rule(row)


def test_wecom_rule(db: Session, rule_id: str) -> dict:
    from app.services.wecom_notify_service import send_wecom_markdown_to_url

    seed_default_wecom_notify(db)
    row = _get_rule_by_external_id(db, rule_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="触发规则不存在")
    channel = row.channel
    webhook_url = (channel.webhook_url if channel else "") or ""
    webhook_url = webhook_url.strip()
    if not webhook_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请先填写通道 Webhook 地址")
    template = validate_template_markdown(row.event_key, row.template_markdown or get_default_template(row.event_key))
    rendered = render_wecom_template(template, get_test_context(row.event_key))
    content = (
        "## 企业微信规则测试\n"
        f"> 规则: **{row.name or EVENT_LABELS.get(row.event_key, row.event_key)}**\n"
        f"> 场景: **{EVENT_LABELS.get(row.event_key, row.event_key)}**\n"
        f"> 通道: **{channel.name if channel else '-'}**\n"
        f"> 规则开关: **{'开启' if row.is_enabled else '关闭'}**\n"
        f"> 通道开关: **{'开启' if channel and channel.is_enabled else '关闭'}**\n"
        f"> 时间: {now_local().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"{rendered}"
    )
    sent = send_wecom_markdown_to_url(content, webhook_url)
    if not sent:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="规则测试发送失败，请检查 Webhook 地址")
    return {"sent": True, "rule_id": row.business_id}


def delete_wecom_rule(db: Session, rule_id: str) -> None:
    seed_default_wecom_notify(db)
    row = _get_rule_by_external_id(db, rule_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="触发规则不存在")
    db.delete(row)
    db.commit()
