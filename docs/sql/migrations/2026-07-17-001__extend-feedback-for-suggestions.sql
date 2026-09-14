SET @feedback_type_column_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'feedback'
    AND COLUMN_NAME = 'feedback_type'
);

SET @feedback_type_ddl := IF(
  @feedback_type_column_exists = 0,
  'ALTER TABLE feedback ADD COLUMN feedback_type VARCHAR(32) NOT NULL DEFAULT ''general'' AFTER content',
  'SELECT 1'
);

PREPARE stmt FROM @feedback_type_ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @attachments_json_column_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'feedback'
    AND COLUMN_NAME = 'attachments_json'
);

SET @attachments_json_ddl := IF(
  @attachments_json_column_exists = 0,
  'ALTER TABLE feedback ADD COLUMN attachments_json TEXT NULL AFTER feedback_type',
  'SELECT 1'
);

PREPARE stmt FROM @attachments_json_ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE feedback
SET feedback_type = 'general'
WHERE feedback_type IS NULL OR feedback_type = '';

UPDATE feedback
SET attachments_json = '[]'
WHERE attachments_json IS NULL OR attachments_json = '';

SET @feedback_type_index_exists := (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'feedback'
    AND INDEX_NAME = 'ix_feedback_feedback_type'
);

SET @feedback_type_index_ddl := IF(
  @feedback_type_index_exists = 0,
  'CREATE INDEX ix_feedback_feedback_type ON feedback (feedback_type)',
  'SELECT 1'
);

PREPARE stmt FROM @feedback_type_index_ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
