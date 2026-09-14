-- 新增更新日志表，支持后台完整管理与前台按生效时间展示。
-- 回滚思路：确认无需保留数据后，DROP TABLE update_logs。

CREATE TABLE IF NOT EXISTS update_logs (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    business_id VARCHAR(32) NOT NULL,
    title VARCHAR(200) NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    tag_type VARCHAR(20) NOT NULL DEFAULT 'other',
    effective_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY ix_update_logs_business_id (business_id),
    KEY ix_update_logs_title (title),
    KEY ix_update_logs_tag_type (tag_type),
    KEY ix_update_logs_effective_at (effective_at),
    KEY idx_update_logs_effective_at_id (effective_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
