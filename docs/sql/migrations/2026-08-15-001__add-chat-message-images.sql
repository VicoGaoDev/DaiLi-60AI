-- 影响范围：
-- 1) chat_messages 增加 images_json，保存对话附件图片 URL 列表；
-- 2) 仅扩展 AI 对话消息，不影响生图/视频任务表。
--
-- 回滚思路：
-- 1) ALTER TABLE chat_messages DROP COLUMN images_json;

ALTER TABLE chat_messages
  ADD COLUMN images_json TEXT NULL;

UPDATE chat_messages
SET images_json = '[]'
WHERE images_json IS NULL;
