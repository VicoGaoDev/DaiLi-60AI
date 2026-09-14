SET @column_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'api_keys'
    AND COLUMN_NAME = 'cos_upload_domain'
);

SET @ddl := IF(
  @column_exists = 0,
  'ALTER TABLE api_keys ADD COLUMN cos_upload_domain VARCHAR(500) NOT NULL DEFAULT '''' AFTER cos_region',
  'SELECT 1'
);

PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
