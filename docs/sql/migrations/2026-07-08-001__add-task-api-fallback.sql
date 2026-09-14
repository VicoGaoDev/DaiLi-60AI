ALTER TABLE external_api_scene_bindings
  ADD COLUMN backup_api_config_id BIGINT NULL;

ALTER TABLE tasks
  ADD COLUMN used_fallback_api TINYINT(1) NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS task_api_attempts (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  task_id BIGINT NOT NULL,
  image_id BIGINT NULL,
  image_index INT NULL,
  api_config_id BIGINT NULL,
  api_config_name VARCHAR(100) NOT NULL DEFAULT '',
  attempt_index INT NOT NULL DEFAULT 1,
  is_fallback TINYINT(1) NOT NULL DEFAULT 0,
  status VARCHAR(20) NOT NULL DEFAULT 'failed',
  http_status INT NULL,
  error_message TEXT NULL,
  duration_ms INT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_api_attempts_task_id (task_id),
  INDEX idx_task_api_attempts_image_id (image_id)
);
