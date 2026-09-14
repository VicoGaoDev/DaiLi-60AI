from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.services.daily_report_service import (
    collect_online_payment_stats,
    get_previous_day_window,
)
from app.services.payment_service import parse_alipay_payment_time


class DailyReportWindowTests(unittest.TestCase):
    def test_utc_reference_is_converted_to_beijing_day(self):
        reference = datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc)
        start_at, end_at = get_previous_day_window(reference)
        self.assertEqual(start_at, datetime(2026, 9, 1, 0, 0))
        self.assertEqual(end_at, datetime(2026, 9, 2, 0, 0))


class AlipayPaymentTimeTests(unittest.TestCase):
    def test_parses_alipay_gmt_payment_as_beijing_naive_time(self):
        result = parse_alipay_payment_time(
            {"gmt_payment": "2026-09-01 23:59:58"}
        )
        self.assertEqual(result, datetime(2026, 9, 1, 23, 59, 58))

    def test_invalid_payment_time_falls_back_cleanly(self):
        self.assertIsNone(parse_alipay_payment_time({}))
        self.assertIsNone(parse_alipay_payment_time({"gmt_payment": "invalid"}))


class OnlinePaymentRevenueTests(unittest.TestCase):
    def test_revenue_uses_paid_at_instead_of_credited_at(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE payment_orders (
                    id INTEGER PRIMARY KEY,
                    amount_fen INTEGER NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    paid_at DATETIME,
                    credited_at DATETIME,
                    notify_payload TEXT
                )
            """))
            conn.execute(text("""
                INSERT INTO payment_orders
                    (id, amount_fen, status, paid_at, credited_at, notify_payload)
                VALUES
                    (1, 1000, 'credited', '2026-09-02 00:01:00', '2026-09-02 00:01:00',
                     '{"gmt_payment":"2026-09-01 23:59:00"}'),
                    (2, 2000, 'credited', '2026-09-01 23:59:00', '2026-09-01 23:59:00',
                     '{"gmt_payment":"2026-09-02 00:01:00"}'),
                    (3, 3000, 'created', '2026-09-01 12:00:00', '2026-09-01 12:00:00', '{}')
            """))

        with Session(engine) as db:
            revenue_fen, count = collect_online_payment_stats(
                db,
                start_at=datetime(2026, 9, 1, 0, 0),
                end_at=datetime(2026, 9, 2, 0, 0),
            )

        self.assertEqual(revenue_fen, 1000)
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
