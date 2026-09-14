-- 影响范围：
-- 1) 新增 generation_scene_categories 表，用于运营侧管理生图场景分类；
-- 2) 分类通过 scene_type 区分文生图 / 图编辑，scene_keys_json 只引用同类型场景；
-- 3) 不改 external_api_scene_bindings。
--
-- 回滚思路：
-- 1) 若尚未发布依赖代码，可直接 DROP TABLE generation_scene_categories；
-- 2) 本脚本不改已有场景或任务数据。

CREATE TABLE IF NOT EXISTS generation_scene_categories (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL,
  description VARCHAR(255) NOT NULL DEFAULT '',
  scene_type VARCHAR(20) NOT NULL DEFAULT 'generate',
  scene_keys_json TEXT NOT NULL,
  sort_order INT NOT NULL DEFAULT 100,
  status VARCHAR(20) NOT NULL DEFAULT 'enabled',
  is_deleted TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_generation_scene_categories_sort (sort_order, id),
  KEY idx_generation_scene_categories_status (status, is_deleted),
  KEY idx_generation_scene_categories_scene_type (scene_type, is_deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
