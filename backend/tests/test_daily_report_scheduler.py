from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.daily_report_run import DailyReportRun
from app.services.daily_report_scheduler import (
    _claim_report,
    next_midnight,
    seconds_until_next_midnight,
)


class DailyReportScheduleTests(unittest.TestCase):
    def test_next_midnight_uses_local_calendar_day(self):
        moment = datetime(2026, 9, 1, 21, 49, 30)
        self.assertEqual(next_midnight(moment), datetime(2026, 9, 2, 0, 0))
        self.assertEqual(seconds_until_next_midnight(moment), 2 * 3600 + 10 * 60 + 30)

    def test_exact_midnight_waits_until_next_day(self):
        moment = datetime(2026, 9, 2, 0, 0)
        self.assertEqual(next_midnight(moment), datetime(2026, 9, 3, 0, 0))
        self.assertEqual(seconds_until_next_midnight(moment), 24 * 3600)


class DailyReportClaimTests(unittest.TestCase):
    def test_report_date_can_only_be_claimed_once(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        DailyReportRun.__table__.create(bind=engine)
        report_date = date(2026, 9, 1)

        with Session(engine) as db:
            self.assertTrue(_claim_report(db, report_date))
        with Session(engine) as db:
            row = db.query(DailyReportRun).one()
            self.assertEqual(row.status, "sending")
            self.assertFalse(
                _claim_report(
                    db,
                    report_date,
                    current_time=row.updated_at + timedelta(minutes=1),
                )
            )

    def test_stale_sending_claim_can_be_recovered(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        DailyReportRun.__table__.create(bind=engine)
        report_date = date(2026, 9, 1)
        now_value = datetime(2026, 9, 2, 1, 0)
        with Session(engine) as db:
            db.add(
                DailyReportRun(
                    report_date=report_date,
                    status="sending",
                    updated_at=now_value - timedelta(hours=1),
                )
            )
            db.commit()
        with Session(engine) as db:
            self.assertTrue(
                _claim_report(db, report_date, current_time=now_value)
            )


if __name__ == "__main__":
    unittest.main()
