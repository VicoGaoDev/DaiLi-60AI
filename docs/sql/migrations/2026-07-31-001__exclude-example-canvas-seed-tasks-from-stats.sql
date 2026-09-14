-- 为示例 Canvas 复制时生成的种子任务增加显式标记，便于后台统计排除。
-- 回滚思路：确认无需保留该标记后，ALTER TABLE tasks DROP COLUMN is_example_template_seed。

ALTER TABLE tasks
    ADD COLUMN is_example_template_seed BOOLEAN NOT NULL DEFAULT 0 AFTER used_fallback_api;

-- 回填历史示例 Canvas 复制任务：
-- 1. 任务挂在 source_example_id 非空的画布上
-- 2. 未扣积分
-- 3. 没有真实请求/入队痕迹
UPDATE tasks t
JOIN user_canvas c ON c.id = t.canvas_id
SET t.is_example_template_seed = 1
WHERE c.source_example_id IS NOT NULL
  AND COALESCE(t.credit_cost, 0) = 0
  AND COALESCE(t.provider_task_id, '') = ''
  AND t.enqueued_at IS NULL
  AND t.request_started_at IS NULL
  AND t.request_finished_at IS NULL;
