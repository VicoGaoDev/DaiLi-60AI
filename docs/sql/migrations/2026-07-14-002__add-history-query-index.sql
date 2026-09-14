SET @index_exists := (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND INDEX_NAME = 'idx_tasks_user_deleted_canvas_board_created'
);

SET @ddl := IF(
  @index_exists = 0,
  'CREATE INDEX idx_tasks_user_deleted_canvas_board_created ON tasks (user_id, is_deleted, canvas_id, board_id, created_at)',
  'SELECT 1'
);

PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
