-- 影响范围：优化后台/历史卡片首页按 created_at 倒序分页的任务候选查询。
-- 回滚思路：如需回滚，可执行 DROP INDEX idx_tasks_seed_created_id_user ON tasks。
-- 执行前置：建议低峰期执行；代码发布前先完成该索引创建。

SET @index_exists := (
  SELECT COUNT(*)
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND INDEX_NAME = 'idx_tasks_seed_created_id_user'
);

SET @ddl := IF(
  @index_exists = 0,
  'CREATE INDEX idx_tasks_seed_created_id_user ON tasks (is_example_template_seed, created_at, id, user_id)',
  'SELECT 1'
);

PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
