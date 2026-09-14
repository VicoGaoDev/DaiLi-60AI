-- 影响范围：记录每日营业额日报发送状态，避免多 Web Worker 或 Celery 重复发送。
-- 回滚思路：DROP TABLE daily_report_runs;

CREATE TABLE IF NOT EXISTS daily_report_runs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  report_date DATE NOT NULL,
  status VARCHAR(20) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_daily_report_runs_report_date (report_date)
);
