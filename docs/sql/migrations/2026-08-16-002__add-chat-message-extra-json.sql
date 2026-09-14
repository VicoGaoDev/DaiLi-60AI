-- 影响范围：
-- 1) chat_messages 增加 extra_json，保存对话生图确认卡片与任务 ID；
-- 2) 仅扩展 AI 对话消息，不影响生图任务表。
--
-- 回滚思路：
-- 1) ALTER TABLE chat_messages DROP COLUMN extra_json;

ALTER TABLE chat_messages
  ADD COLUMN extra_json TEXT NULL;
