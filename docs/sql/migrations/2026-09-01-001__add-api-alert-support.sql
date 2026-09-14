-- 影响范围：记录每张图片的接口调用起止时间，供接口质量告警按完成时间窗口聚合；
--           同时用时间槽记录避免重复发送。
-- 回滚思路：DROP INDEX idx_images_request_finished_at ON images;
--           ALTER TABLE images DROP COLUMN request_started_at, DROP COLUMN request_finished_at;
--           DROP TABLE api_alert_runs;
-- 执行前置：建议低峰期执行；代码发布前先完成该迁移。

SET @column_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'images'
    AND COLUMN_NAME = 'request_started_at'
);

SET @ddl := IF(
  @column_exists = 0,
  'ALTER TABLE images ADD COLUMN request_started_at DATETIME NULL',
  'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @column_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'images'
    AND COLUMN_NAME = 'request_finished_at'
);

SET @ddl := IF(
  @column_exists = 0,
  'ALTER TABLE images ADD COLUMN request_finished_at DATETIME NULL',
  'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @index_exists := (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'images'
    AND INDEX_NAME = 'idx_images_request_finished_at'
);

SET @ddl := IF(
  @index_exists = 0,
  'CREATE INDEX idx_images_request_finished_at ON images (request_finished_at)',
  'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS api_alert_runs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  slot_start DATETIME NOT NULL,
  alert_type VARCHAR(20) NOT NULL,
  status VARCHAR(20) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_api_alert_runs_slot_type (slot_start, alert_type)
);
