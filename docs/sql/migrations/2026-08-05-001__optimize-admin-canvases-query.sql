SET @index_exists := (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'user_canvas'
    AND INDEX_NAME = 'idx_user_canvas_updated_id'
);

SET @ddl := IF(
  @index_exists = 0,
  'CREATE INDEX idx_user_canvas_updated_id ON user_canvas (updated_at, id)',
  'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @index_exists := (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'canvas_nodes'
    AND INDEX_NAME = 'idx_canvas_nodes_canvas_updated_id'
);

SET @ddl := IF(
  @index_exists = 0,
  'CREATE INDEX idx_canvas_nodes_canvas_updated_id ON canvas_nodes (canvas_id, updated_at, id)',
  'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
