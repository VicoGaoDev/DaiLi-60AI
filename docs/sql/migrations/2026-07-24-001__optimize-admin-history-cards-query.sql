SET @index_exists := (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND INDEX_NAME = 'idx_tasks_user_status_deleted_created_id'
);

SET @ddl := IF(
  @index_exists = 0,
  'CREATE INDEX idx_tasks_user_status_deleted_created_id ON tasks (user_id, status, is_deleted, created_at, id)',
  'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @index_exists := (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND INDEX_NAME = 'idx_tasks_user_status_created_id'
);

SET @ddl := IF(
  @index_exists = 0,
  'CREATE INDEX idx_tasks_user_status_created_id ON tasks (user_id, status, created_at, id)',
  'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @index_exists := (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND INDEX_NAME = 'idx_tasks_user_created_id'
);

SET @ddl := IF(
  @index_exists = 0,
  'CREATE INDEX idx_tasks_user_created_id ON tasks (user_id, created_at, id)',
  'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @index_exists := (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND INDEX_NAME = 'idx_tasks_created_status_source_mode_model_user'
);

SET @ddl := IF(
  @index_exists = 0,
  'CREATE INDEX idx_tasks_created_status_source_mode_model_user ON tasks (created_at, status, source, mode, model, user_id)',
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
    AND INDEX_NAME = 'idx_images_task_deleted_id'
);

SET @ddl := IF(
  @index_exists = 0,
  'CREATE INDEX idx_images_task_deleted_id ON images (task_id, is_deleted, id)',
  'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @index_exists := (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'credit_logs'
    AND INDEX_NAME = 'idx_credit_logs_type_desc_user_created_id'
);

SET @ddl := IF(
  @index_exists = 0,
  'CREATE INDEX idx_credit_logs_type_desc_user_created_id ON credit_logs (type, description(191), user_id, created_at, id)',
  'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @index_exists := (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'credit_logs'
    AND INDEX_NAME = 'idx_credit_logs_task_type_desc'
);

SET @ddl := IF(
  @index_exists = 0,
  'CREATE INDEX idx_credit_logs_task_type_desc ON credit_logs (task_id, type, description(191))',
  'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @index_exists := (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'prompt_history'
    AND INDEX_NAME = 'idx_prompt_history_mode_created_id_user'
);

SET @ddl := IF(
  @index_exists = 0,
  'CREATE INDEX idx_prompt_history_mode_created_id_user ON prompt_history (mode, created_at, id, user_id)',
  'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
