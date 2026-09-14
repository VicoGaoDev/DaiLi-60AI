CREATE TABLE IF NOT EXISTS example_canvas_projects (
    id INTEGER NOT NULL AUTO_INCREMENT,
    source_canvas_id INTEGER NOT NULL,
    source_project_id VARCHAR(16) NOT NULL,
    title VARCHAR(100) NOT NULL DEFAULT '',
    subtitle VARCHAR(255) NOT NULL DEFAULT '',
    cover_url VARCHAR(1000) NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    sort_order INTEGER NOT NULL DEFAULT 0,
    preview_urls_json TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_by INTEGER NULL,
    updated_by INTEGER NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_example_canvas_projects_source_canvas_id (source_canvas_id),
    UNIQUE KEY uq_example_canvas_projects_source_project_id (source_project_id),
    INDEX idx_example_canvas_projects_status_sort (status, sort_order, id),
    INDEX idx_example_canvas_projects_created_by (created_by),
    INDEX idx_example_canvas_projects_updated_by (updated_by),
    CONSTRAINT fk_example_canvas_projects_source_canvas_id FOREIGN KEY (source_canvas_id) REFERENCES user_canvas (id),
    CONSTRAINT fk_example_canvas_projects_created_by FOREIGN KEY (created_by) REFERENCES users (id),
    CONSTRAINT fk_example_canvas_projects_updated_by FOREIGN KEY (updated_by) REFERENCES users (id)
);

SET @has_source_example_id := (
    SELECT COUNT(*)
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'user_canvas'
      AND COLUMN_NAME = 'source_example_id'
);
SET @ddl := IF(
    @has_source_example_id = 0,
    'ALTER TABLE user_canvas ADD COLUMN source_example_id INTEGER NULL',
    'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @has_idx_source_example_id := (
    SELECT COUNT(*)
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'user_canvas'
      AND INDEX_NAME = 'idx_user_canvas_source_example_id'
);
SET @ddl := IF(
    @has_idx_source_example_id = 0,
    'CREATE INDEX idx_user_canvas_source_example_id ON user_canvas (source_example_id)',
    'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
