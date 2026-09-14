-- 影响范围：
-- 1) 为管理后台全站会话列表增加 (is_deleted, last_message_at, id) 索引；
-- 2) 回填历史空 last_message_at，保证游标排序字段可走索引；
-- 3) 配合游标翻页，避免 OFFSET 深分页扫过大量历史行。
--
-- 回滚思路：
-- 1) ALTER TABLE chat_sessions DROP INDEX idx_chat_sessions_admin_list;

UPDATE chat_sessions
SET last_message_at = COALESCE(last_message_at, updated_at, created_at)
WHERE last_message_at IS NULL;

ALTER TABLE chat_sessions
  ADD INDEX idx_chat_sessions_admin_list (is_deleted, last_message_at, id);
