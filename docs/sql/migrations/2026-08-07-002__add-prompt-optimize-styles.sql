-- 影响范围：
-- 1) 新增 prompt_optimize_styles 表，管理提示词优化系统风格；
-- 2) 为 prompt_optimize_tasks 增加 style_id / style_name_snapshot 字段；
-- 3) 插入默认“通用优化”风格，保证上线后用户端可直接使用。
--
-- 回滚思路：
-- 1) 若尚未发布依赖代码，可先删除新增字段与新表；
-- 2) 本脚本不会删除已有 prompt_optimize_tasks 记录。

CREATE TABLE IF NOT EXISTS prompt_optimize_styles (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL,
  description VARCHAR(255) NOT NULL DEFAULT '',
  style_prompt TEXT NOT NULL,
  sort_order INT NOT NULL DEFAULT 100,
  status VARCHAR(20) NOT NULL DEFAULT 'enabled',
  is_default TINYINT(1) NOT NULL DEFAULT 0,
  is_deleted TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_prompt_optimize_styles_sort (sort_order, id),
  KEY idx_prompt_optimize_styles_status_default (status, is_default, is_deleted)
);

ALTER TABLE prompt_optimize_tasks
  ADD COLUMN style_id INT NULL,
  ADD COLUMN style_name_snapshot VARCHAR(100) NOT NULL DEFAULT '';

CREATE INDEX idx_prompt_optimize_tasks_style_id ON prompt_optimize_tasks (style_id);

INSERT INTO prompt_optimize_styles (
  name,
  description,
  style_prompt,
  sort_order,
  status,
  is_default,
  is_deleted
)
SELECT
  '通用优化',
  '默认风格，适合通用中文生图提示词补全',
  '在保留用户原始意图前提下，补全构图、镜头、光线、色彩、材质、氛围和画面细节，输出适合直接生图的中文提示词。',
  10,
  'enabled',
  1,
  0
WHERE NOT EXISTS (
  SELECT 1
  FROM prompt_optimize_styles
  WHERE name = '通用优化'
    AND is_deleted = 0
);
