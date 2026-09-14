from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models.api_alert_run import ApiAlertRun
from app.services.api_alert_service import (
    ApiAlertApiStat,
    ApiAlertStats,
    _claim_run,
    align_slot_start,
    build_overall_markdown,
    build_per_api_markdown,
    collect_api_alert_stats,
    evaluate_api_alerts,
    next_slot_start,
    seconds_until_next_slot,
)
from app.services.wecom_notify_service import (
    is_wecom_alert_enabled,
    send_wecom_alert_markdown,
    send_wecom_markdown,
)


def _api(
    *,
    name: str,
    image_count: int,
    success_count: int,
    avg_duration_seconds: float | None,
    api_config_id: int | None = 1,
) -> ApiAlertApiStat:
    return ApiAlertApiStat(
        api_config_id=api_config_id,
        api_config_name=name,
        image_count=image_count,
        success_count=success_count,
        avg_duration_seconds=avg_duration_seconds,
    )


def _stats(apis: list[ApiAlertApiStat], *, overall_image_count: int, overall_success_count: int) -> ApiAlertStats:
    start_at = datetime(2026, 9, 1, 15, 30)
    end_at = datetime(2026, 9, 1, 16, 30)
    return ApiAlertStats(
        start_at=start_at,
        end_at=end_at,
        apis=apis,
        overall_image_count=overall_image_count,
        overall_success_count=overall_success_count,
        api_count=len(apis),
    )


class ApiAlertSlotTests(unittest.TestCase):
    def test_align_slot_start_floors_to_interval(self):
        moment = datetime(2026, 9, 1, 16, 17, 42)
        self.assertEqual(align_slot_start(moment, 30), datetime(2026, 9, 1, 16, 0))
        self.assertEqual(align_slot_start(datetime(2026, 9, 1, 16, 30), 30), datetime(2026, 9, 1, 16, 30))

    def test_next_slot_is_always_in_the_future(self):
        moment = datetime(2026, 9, 1, 16, 29, 50)
        self.assertEqual(next_slot_start(moment, 30), datetime(2026, 9, 1, 16, 30))
        self.assertAlmostEqual(seconds_until_next_slot(moment, 30), 10.0)
        self.assertGreater(seconds_until_next_slot(datetime(2026, 9, 1, 16, 30), 30), 0)

    def test_alignment_supports_intervals_longer_than_one_hour(self):
        moment = datetime(2026, 9, 1, 16, 47)
        self.assertEqual(align_slot_start(moment, 90), datetime(2026, 9, 1, 16, 30))
        self.assertEqual(next_slot_start(moment, 90), datetime(2026, 9, 1, 18, 0))
        late = datetime(2026, 9, 1, 23, 50)
        next_slot = next_slot_start(late, 100)
        self.assertGreater(next_slot, late)
        self.assertEqual(align_slot_start(next_slot, 100), next_slot)


class ApiAlertEvaluateTests(unittest.TestCase):
    def test_per_api_success_rate_below_threshold(self):
        stats = _stats([_api(name="foo", image_count=16, success_count=10, avg_duration_seconds=20)], overall_image_count=16, overall_success_count=10)
        decision = evaluate_api_alerts(stats, min_call_count=5, overall_min_call_count=10, success_rate_threshold=80, avg_duration_seconds=150)
        self.assertEqual(len(decision.per_api_alerts), 1)
        self.assertIn("success_rate", decision.per_api_alerts[0].alert_reasons)
        self.assertTrue(decision.overall_alert)

    def test_per_api_ignores_small_sample(self):
        stats = _stats([_api(name="foo", image_count=4, success_count=1, avg_duration_seconds=20)], overall_image_count=4, overall_success_count=1)
        decision = evaluate_api_alerts(stats, min_call_count=5, overall_min_call_count=10, success_rate_threshold=80, avg_duration_seconds=150)
        self.assertEqual(decision.per_api_alerts, [])
        self.assertFalse(decision.overall_alert)

    def test_default_per_api_requires_ten_images(self):
        stats = _stats(
            [_api(name="foo", image_count=9, success_count=1, avg_duration_seconds=200)],
            overall_image_count=9,
            overall_success_count=1,
        )
        decision = evaluate_api_alerts(stats)
        self.assertEqual(decision.per_api_alerts, [])
        self.assertFalse(decision.overall_alert)

    def test_per_api_duration_threshold(self):
        stats = _stats([_api(name="slow", image_count=8, success_count=8, avg_duration_seconds=182)], overall_image_count=8, overall_success_count=8)
        decision = evaluate_api_alerts(stats, min_call_count=5, overall_min_call_count=10, success_rate_threshold=80, avg_duration_seconds=150)
        self.assertEqual(decision.per_api_alerts[0].alert_reasons, ("duration",))
        self.assertFalse(decision.overall_alert)

    def test_overall_requires_ten_images(self):
        stats = _stats(
            [_api(name="a", image_count=5, success_count=5, avg_duration_seconds=10), _api(name="b", image_count=4, success_count=1, avg_duration_seconds=10)],
            overall_image_count=9,
            overall_success_count=6,
        )
        decision = evaluate_api_alerts(stats, min_call_count=5, overall_min_call_count=10, success_rate_threshold=80, avg_duration_seconds=150)
        self.assertFalse(decision.overall_alert)
        self.assertEqual(decision.per_api_alerts, [])

    def test_healthy_window_is_silent(self):
        stats = _stats([_api(name="ok", image_count=20, success_count=19, avg_duration_seconds=30)], overall_image_count=20, overall_success_count=19)
        decision = evaluate_api_alerts(stats, min_call_count=5, overall_min_call_count=10, success_rate_threshold=80, avg_duration_seconds=150)
        self.assertEqual(decision.per_api_alerts, [])
        self.assertFalse(decision.overall_alert)

    def test_thresholds_use_unrounded_values(self):
        stats = _stats(
            [_api(name="edge", image_count=10000, success_count=7998, avg_duration_seconds=150.04)],
            overall_image_count=10000,
            overall_success_count=7998,
        )
        decision = evaluate_api_alerts(
            stats,
            min_call_count=5,
            overall_min_call_count=10,
            success_rate_threshold=80,
            avg_duration_seconds=150,
        )
        self.assertEqual(
            decision.per_api_alerts[0].alert_reasons,
            ("success_rate", "duration"),
        )
        self.assertTrue(decision.overall_alert)


class ApiAlertRunClaimTests(unittest.TestCase):
    def test_claim_is_committed_before_send_and_is_idempotent(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        ApiAlertRun.__table__.create(bind=engine)
        slot = datetime(2026, 9, 1, 16, 30)
        with Session(engine) as db:
            self.assertTrue(_claim_run(db, slot, "per_api"))
        with Session(engine) as db:
            row = db.query(ApiAlertRun).one()
            self.assertEqual(row.status, "sending")
            self.assertFalse(_claim_run(db, slot, "per_api"))


class ApiAlertQueryTests(unittest.TestCase):
    def test_query_limits_attempts_to_window_and_uses_latest_provider(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")

        @event.listens_for(engine, "connect")
        def add_unix_timestamp(dbapi_connection, _connection_record):
            def unix_timestamp(value):
                if value is None:
                    return None
                return datetime.fromisoformat(str(value)).timestamp()

            dbapi_connection.create_function("unix_timestamp", 1, unix_timestamp)

        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY,
                    is_example_template_seed BOOLEAN,
                    provider_task_id VARCHAR(255),
                    request_started_at DATETIME,
                    request_finished_at DATETIME,
                    created_at DATETIME
                )
            """))
            conn.execute(text("""
                CREATE TABLE images (
                    id INTEGER PRIMARY KEY,
                    task_id INTEGER NOT NULL,
                    status VARCHAR(20),
                    error_message TEXT,
                    request_started_at DATETIME,
                    request_finished_at DATETIME
                )
            """))
            conn.execute(text("""
                CREATE TABLE task_api_attempts (
                    id INTEGER PRIMARY KEY,
                    image_id INTEGER,
                    api_config_id INTEGER,
                    api_config_name VARCHAR(100),
                    status VARCHAR(20),
                    error_message TEXT,
                    duration_ms INTEGER
                )
            """))
            conn.execute(
                text("""
                    INSERT INTO tasks
                        (id, is_example_template_seed, provider_task_id, request_started_at, request_finished_at, created_at)
                    VALUES
                        (1, 0, '', '2026-09-01 15:00:00', '2026-09-01 16:10:00', '2026-09-01 15:00:00'),
                        (2, 0, '', '2026-09-01 12:00:00', '2026-09-01 12:01:00', '2026-09-01 12:00:00'),
                        (3, 0, 'provider-async-1', '2026-09-01 16:00:00', '2026-09-01 16:10:00', '2026-09-01 16:00:00')
                """)
            )
            conn.execute(
                text("""
                    INSERT INTO images
                        (id, task_id, status, error_message, request_started_at, request_finished_at)
                    VALUES
                        (10, 1, 'success', '', '2026-09-01 16:08:00', '2026-09-01 16:10:00'),
                        (11, 1, 'failed', '接口超时', '2026-09-01 16:06:00', '2026-09-01 16:10:00'),
                        (12, 1, 'failed', '生成的图片存在安全风险', '2026-09-01 16:05:00', '2026-09-01 16:10:00'),
                        (13, 1, 'failed', '提示词或参考图审核未通过', '2026-09-01 16:04:00', '2026-09-01 16:10:00'),
                        (14, 1, 'failed', 'prompt moderation failed by provider', '2026-09-01 16:03:00', '2026-09-01 16:10:00'),
                        (15, 1, 'failed', 'input image violates content policy', '2026-09-01 16:02:00', '2026-09-01 16:10:00'),
                        (16, 1, 'success', '', '2026-09-01 16:01:00', '2026-09-01 16:10:00'),
                        (20, 2, 'failed', '接口超时', '2026-09-01 12:00:00', '2026-09-01 12:01:00'),
                        (30, 3, 'success', '', '2026-09-01 16:00:00', '2026-09-01 16:10:00')
                """)
            )
            conn.execute(
                text("""
                    INSERT INTO task_api_attempts
                        (id, image_id, api_config_id, api_config_name, status, error_message, duration_ms)
                    VALUES
                        (1, 10, 1, 'primary', 'failed', 'HTTP 500', 30000),
                        (2, 10, 2, 'fallback', 'success', '', 120000),
                        (3, 11, 1, 'primary', 'failed', '接口超时', 240000),
                        (4, 20, 9, 'historical', 'failed', '接口超时', 1000),
                        (5, 12, 1, 'primary', 'failed', '生成的图片存在安全风险', 250000),
                        (6, 13, 2, 'fallback', 'failed', '提示词或参考图审核未通过', 250000),
                        (7, 14, 1, 'primary', 'failed', 'prompt moderation failed by provider', 250000),
                        (8, 15, 2, 'fallback', 'failed', 'input image violates content policy', 250000),
                        (9, 16, 1, 'primary', 'failed', 'prompt moderation failed by provider', 110000),
                        (10, 16, 2, 'fallback', 'success', '', 90000),
                        (11, 30, 3, 'async', 'success', '', 1000),
                        (12, 30, 3, 'async', 'success', '', 2000)
                """)
            )

        with Session(engine) as db:
            stats = collect_api_alert_stats(
                db,
                start_at=datetime(2026, 9, 1, 15, 30),
                end_at=datetime(2026, 9, 1, 16, 30),
            )

        self.assertEqual(stats.overall_image_count, 5)
        self.assertEqual(stats.overall_success_count, 3)
        by_name = {item.api_config_name: item for item in stats.apis}
        self.assertEqual(set(by_name), {"primary", "fallback", "async"})
        self.assertEqual(by_name["primary"].image_count, 2)
        self.assertEqual(by_name["primary"].success_count, 0)
        self.assertAlmostEqual(by_name["primary"].avg_duration_seconds, 135.0)
        self.assertEqual(by_name["fallback"].image_count, 2)
        self.assertEqual(by_name["fallback"].success_count, 2)
        self.assertAlmostEqual(by_name["fallback"].avg_duration_seconds, 105.0)
        self.assertEqual(by_name["async"].image_count, 1)
        self.assertEqual(by_name["async"].success_count, 1)
        self.assertAlmostEqual(by_name["async"].avg_duration_seconds, 600.0)


class ApiAlertMarkdownTests(unittest.TestCase):
    def test_per_api_markdown_lists_failing_apis(self):
        stats = _stats([_api(name="foo-api", image_count=16, success_count=10, avg_duration_seconds=168.2)], overall_image_count=16, overall_success_count=10)
        decision = evaluate_api_alerts(stats, min_call_count=5, overall_min_call_count=10, success_rate_threshold=80, avg_duration_seconds=150)
        content = build_per_api_markdown(stats, decision.per_api_alerts)
        self.assertIn("接口质量告警", content)
        self.assertIn("foo-api", content)
        self.assertIn("62.5%", content)
        self.assertIn("168.2s", content)

    def test_overall_markdown_includes_totals(self):
        stats = _stats([_api(name="foo-api", image_count=16, success_count=10, avg_duration_seconds=20)], overall_image_count=172, overall_success_count=128)
        content = build_overall_markdown(stats)
        self.assertIn("全量接口成功率告警", content)
        self.assertIn("74.4%", content)
        self.assertIn("128/172", content)
        self.assertIn("涉及接口数: **1**", content)


class WecomAlertChannelTests(unittest.TestCase):
    def test_alert_channel_requires_dedicated_webhook(self):
        with (
            patch.object(settings, "API_ALERT_ENABLED", True),
            patch.object(settings, "WECOM_ALERT_WEBHOOK_URL", ""),
            patch.object(settings, "WECOM_NOTIFY_ENABLED", True),
            patch.object(settings, "WECOM_WEBHOOK_URL", "https://biz.example/hook"),
        ):
            self.assertFalse(is_wecom_alert_enabled())

    def test_business_and_alert_webhooks_stay_isolated(self):
        posted = []

        def fake_post(url, json, timeout):
            posted.append(url)

            class Response:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"errcode": 0}

            return Response()

        with (
            patch.object(settings, "API_ALERT_ENABLED", True),
            patch.object(settings, "WECOM_ALERT_WEBHOOK_URL", "https://alert.example/hook"),
            patch.object(settings, "WECOM_NOTIFY_ENABLED", True),
            patch.object(settings, "WECOM_WEBHOOK_URL", "https://biz.example/hook"),
            patch("app.services.wecom_notify_service.httpx.post", side_effect=fake_post),
        ):
            self.assertTrue(is_wecom_alert_enabled())
            self.assertTrue(send_wecom_markdown("biz"))
            self.assertTrue(send_wecom_alert_markdown("alert"))
        self.assertEqual(posted, ["https://biz.example/hook", "https://alert.example/hook"])


if __name__ == "__main__":
    unittest.main()
