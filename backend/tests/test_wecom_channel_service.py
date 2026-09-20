from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import sessionmaker

from app.models.wecom_notify_rule import WecomNotifyRule
from app.models.wecom_webhook_channel import WecomWebhookChannel
from app.services.wecom_channel_service import (
    EVENT_API_ALERT,
    EVENT_DAILY_REPORT,
    EVENT_OFFLINE_ORDER,
    EVENT_PAYMENT_SUCCESS,
    EVENT_REDEEM_SUCCESS,
    EVENT_USER_REGISTERED,
    _enabled_targets,
    create_wecom_channel,
    create_wecom_rule,
    update_wecom_rule,
    get_default_template,
    match_conditions,
    render_wecom_template,
    resolve_dispatch_targets,
    resolve_dispatch_urls,
    seed_default_wecom_notify,
    test_wecom_rule,
    update_wecom_channel,
    validate_template_markdown,
)
from app.services.wecom_notify_service import dispatch_wecom_event


class WecomConditionTests(unittest.TestCase):
    def test_empty_conditions_always_match(self):
        self.assertTrue(match_conditions({}, {"amount_yuan": 1}))

    def test_min_amount_filters_small_orders(self):
        self.assertFalse(match_conditions({"min_amount_yuan": 100}, {"amount_yuan": 20}))
        self.assertTrue(match_conditions({"min_amount_yuan": 100}, {"amount_yuan": 100}))

    def test_include_gift_false_skips_gift_redeem(self):
        self.assertFalse(match_conditions({"include_gift": False}, {"is_gift": True}))
        self.assertTrue(match_conditions({"include_gift": False}, {"is_gift": False}))

    def test_order_types_filter(self):
        self.assertFalse(match_conditions({"order_types": ["refund"]}, {"order_type": "purchase"}))
        self.assertTrue(match_conditions({"order_types": ["refund"]}, {"order_type": "refund"}))

    def test_template_render_replaces_known_variables(self):
        self.assertEqual(render_wecom_template("用户 {{user_label}} 金额 {{amount_yuan}}", {"user_label": "张三", "amount_yuan": "9.90"}), "用户 张三 金额 9.90")

    def test_template_render_missing_variable_falls_back(self):
        self.assertEqual(render_wecom_template("用户 {{user_label}}", {}), "用户 -")

    def test_template_render_empty_string_stays_empty(self):
        self.assertEqual(render_wecom_template("{{gift_line}}> 积分", {"gift_line": ""}), "> 积分")

    def test_template_rejects_unknown_variables(self):
        with self.assertRaises(HTTPException):
            validate_template_markdown(EVENT_PAYMENT_SUCCESS, "订单 {{unknown_key}}")


class WecomChannelServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        WecomWebhookChannel.__table__.create(bind=self.engine)
        WecomNotifyRule.__table__.create(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_seed_creates_default_channels_and_rules(self):
        with patch("app.services.wecom_channel_service.settings") as mock_settings:
            mock_settings.WECOM_NOTIFY_ENABLED = True
            mock_settings.WECOM_WEBHOOK_URL = "https://biz.example/hook"
            mock_settings.API_ALERT_ENABLED = True
            mock_settings.WECOM_ALERT_WEBHOOK_URL = "https://alert.example/hook"
            seed_default_wecom_notify(self.db)

        self.assertEqual(self.db.query(WecomWebhookChannel).count(), 2)
        self.assertEqual(self.db.query(WecomNotifyRule).count(), 9)
        payment_urls = _enabled_targets(self.db, EVENT_PAYMENT_SUCCESS, {"amount_yuan": 12})
        alert_urls = _enabled_targets(self.db, EVENT_API_ALERT, {})
        self.assertEqual(payment_urls, ["https://biz.example/hook"])
        self.assertEqual(alert_urls, ["https://alert.example/hook"])
        payment_rule = self.db.query(WecomNotifyRule).filter(WecomNotifyRule.event_key == EVENT_PAYMENT_SUCCESS).one()
        self.assertEqual(payment_rule.template_markdown, get_default_template(EVENT_PAYMENT_SUCCESS))
        seeded_events = {row.event_key for row in self.db.query(WecomNotifyRule).all()}
        self.assertNotIn(EVENT_USER_REGISTERED, seeded_events)
        self.assertNotIn(EVENT_OFFLINE_ORDER, seeded_events)

    def test_disabled_channel_does_not_send(self):
        with patch("app.services.wecom_channel_service.settings") as mock_settings:
            mock_settings.WECOM_NOTIFY_ENABLED = True
            mock_settings.WECOM_WEBHOOK_URL = "https://biz.example/hook"
            mock_settings.API_ALERT_ENABLED = False
            mock_settings.WECOM_ALERT_WEBHOOK_URL = ""
            seed_default_wecom_notify(self.db)
        business = self.db.query(WecomWebhookChannel).filter(WecomWebhookChannel.name == "经营通知").one()
        update_wecom_channel(self.db, business.business_id, is_enabled=False)
        self.assertEqual(_enabled_targets(self.db, EVENT_DAILY_REPORT, {}), [])

    def test_one_event_can_hit_two_channels(self):
        with patch("app.services.wecom_channel_service.settings") as mock_settings:
            mock_settings.WECOM_NOTIFY_ENABLED = True
            mock_settings.WECOM_WEBHOOK_URL = "https://biz.example/hook"
            mock_settings.API_ALERT_ENABLED = False
            mock_settings.WECOM_ALERT_WEBHOOK_URL = ""
            seed_default_wecom_notify(self.db)
        extra = create_wecom_channel(
            self.db,
            name="大额群",
            webhook_url="https://big.example/hook",
            is_enabled=True,
        )
        create_wecom_rule(
            self.db,
            channel_id=extra["id"],
            event_key=EVENT_PAYMENT_SUCCESS,
            conditions={"min_amount_yuan": 50},
        )
        urls = _enabled_targets(self.db, EVENT_PAYMENT_SUCCESS, {"amount_yuan": 80})
        self.assertEqual(sorted(urls), ["https://big.example/hook", "https://biz.example/hook"])
        small = _enabled_targets(self.db, EVENT_PAYMENT_SUCCESS, {"amount_yuan": 10})
        self.assertEqual(small, ["https://biz.example/hook"])

    def test_missing_table_falls_back_to_env(self):
        class BoomSession:
            def query(self, *args, **kwargs):
                raise ProgrammingError("SELECT", {}, Exception("no such table"))

            def rollback(self):
                return None

            def close(self):
                return None

        with (
            patch("app.database.SessionLocal", return_value=BoomSession()),
            patch("app.services.wecom_channel_service.settings") as mock_settings,
        ):
            mock_settings.WECOM_NOTIFY_ENABLED = True
            mock_settings.WECOM_WEBHOOK_URL = "https://biz.example/hook"
            mock_settings.API_ALERT_ENABLED = True
            mock_settings.WECOM_ALERT_WEBHOOK_URL = "https://alert.example/hook"
            self.assertEqual(resolve_dispatch_urls(EVENT_PAYMENT_SUCCESS), ["https://biz.example/hook"])
            self.assertEqual(resolve_dispatch_urls(EVENT_API_ALERT), ["https://alert.example/hook"])

    def test_existing_channel_with_no_rules_does_not_fall_back_to_env(self):
        self.db.add(
            WecomWebhookChannel(
                business_id="channel_without_rules",
                name="空规则通道",
                webhook_url="https://channel.example/hook",
                is_enabled=True,
            )
        )
        self.db.commit()
        with (
            patch("app.database.SessionLocal", return_value=self.db),
            patch("app.services.wecom_channel_service.settings") as mock_settings,
        ):
            mock_settings.WECOM_NOTIFY_ENABLED = True
            mock_settings.WECOM_WEBHOOK_URL = "https://env.example/hook"
            self.assertEqual(resolve_dispatch_urls(EVENT_PAYMENT_SUCCESS), [])

    def test_dispatch_sends_to_resolved_urls(self):
        posted = []

        def fake_post(url, json, timeout):
            posted.append((url, json["markdown"]["content"]))

            class Response:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"errcode": 0}

            return Response()

        with (
            patch(
                "app.services.wecom_channel_service.resolve_dispatch_targets",
                return_value=[
                    {"webhook_url": "https://a.example/hook", "template_markdown": "你好 {{user_label}}"},
                    {"webhook_url": "https://b.example/hook", "template_markdown": ""},
                ],
            ),
            patch("app.services.wecom_notify_service.httpx.post", side_effect=fake_post),
        ):
            self.assertTrue(dispatch_wecom_event(EVENT_PAYMENT_SUCCESS, "hello", {"amount_yuan": 9, "user_label": "张三"}))
        self.assertEqual(posted, [("https://a.example/hook", "你好 张三"), ("https://b.example/hook", "hello")])

    def test_rule_test_send_renders_template_with_sample_context(self):
        with patch("app.services.wecom_channel_service.settings") as mock_settings:
            mock_settings.WECOM_NOTIFY_ENABLED = True
            mock_settings.WECOM_WEBHOOK_URL = "https://biz.example/hook"
            mock_settings.API_ALERT_ENABLED = False
            mock_settings.WECOM_ALERT_WEBHOOK_URL = ""
            seed_default_wecom_notify(self.db)
        business = self.db.query(WecomWebhookChannel).filter(WecomWebhookChannel.name == "经营通知").one()
        rule = create_wecom_rule(
            self.db,
            channel_id=business.business_id,
            event_key=EVENT_PAYMENT_SUCCESS,
            template_markdown="测试订单 {{order_no}}",
        )
        sent = {}

        def fake_send(content, webhook_url):
            sent["content"] = content
            sent["webhook_url"] = webhook_url
            return True

        with patch("app.services.wecom_notify_service.send_wecom_markdown_to_url", side_effect=fake_send):
            self.assertTrue(test_wecom_rule(self.db, rule["id"])["sent"])
        self.assertEqual(sent["webhook_url"], "https://biz.example/hook")
        self.assertIn("测试订单 P202609170001", sent["content"])

    def test_change_event_resets_template_and_conditions_when_not_provided(self):
        with patch("app.services.wecom_channel_service.settings") as mock_settings:
            mock_settings.WECOM_NOTIFY_ENABLED = True
            mock_settings.WECOM_WEBHOOK_URL = "https://biz.example/hook"
            mock_settings.API_ALERT_ENABLED = False
            mock_settings.WECOM_ALERT_WEBHOOK_URL = ""
            seed_default_wecom_notify(self.db)
        business = self.db.query(WecomWebhookChannel).filter(WecomWebhookChannel.name == "经营通知").one()
        rule = create_wecom_rule(
            self.db,
            channel_id=business.business_id,
            event_key=EVENT_PAYMENT_SUCCESS,
            conditions={"min_amount_yuan": 100},
            template_markdown="订单 {{order_no}}",
        )

        updated = update_wecom_rule(self.db, rule["id"], event_key=EVENT_REDEEM_SUCCESS)

        self.assertEqual(updated["event_key"], EVENT_REDEEM_SUCCESS)
        self.assertEqual(updated["conditions"], {})
        self.assertEqual(updated["template_markdown"], get_default_template(EVENT_REDEEM_SUCCESS))


if __name__ == "__main__":
    unittest.main()
