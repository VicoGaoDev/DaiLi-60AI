CREATE INDEX idx_tasks_status_deleted_created
  ON tasks (status, is_deleted, created_at);

CREATE INDEX idx_tasks_user_status_deleted_created
  ON tasks (user_id, status, is_deleted, created_at);

CREATE INDEX idx_images_task_deleted_status_id
  ON images (task_id, is_deleted, status, id);

CREATE INDEX idx_credit_logs_task_type_description
  ON credit_logs (task_id, type, description(191));

CREATE INDEX idx_prompt_history_mode_user_created
  ON prompt_history (mode, user_id, created_at);
