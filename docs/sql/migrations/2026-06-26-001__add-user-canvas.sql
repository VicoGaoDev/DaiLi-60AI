-- Add independent infinite canvas projects and node layout.
-- Execute after 2026-06-24-001__add-user-boards.sql and before deploying code that uses /api/canvases.

CREATE TABLE IF NOT EXISTS user_canvas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  name VARCHAR(100) NOT NULL DEFAULT '',
  viewport_x DOUBLE NOT NULL DEFAULT 0,
  viewport_y DOUBLE NOT NULL DEFAULT 0,
  zoom DOUBLE NOT NULL DEFAULT 0.5,
  is_deleted BOOLEAN NOT NULL DEFAULT 0,
  deleted_at DATETIME NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_user_canvas_user_id (user_id),
  INDEX idx_user_canvas_user_updated_at (user_id, updated_at),
  INDEX idx_user_canvas_user_deleted_updated (user_id, is_deleted, updated_at),
  CONSTRAINT fk_user_canvas_user FOREIGN KEY (user_id) REFERENCES users(id)
);

ALTER TABLE tasks
  ADD COLUMN canvas_id INT NULL;

CREATE INDEX idx_tasks_canvas_id ON tasks (canvas_id);
CREATE INDEX idx_tasks_user_canvas_deleted_created ON tasks (user_id, canvas_id, is_deleted, created_at);

ALTER TABLE tasks
  ADD CONSTRAINT fk_tasks_canvas
  FOREIGN KEY (canvas_id) REFERENCES user_canvas(id)
  ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS canvas_nodes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  canvas_id INT NOT NULL,
  task_id INT NOT NULL,
  x DOUBLE NOT NULL DEFAULT 0,
  y DOUBLE NOT NULL DEFAULT 0,
  width DOUBLE NOT NULL DEFAULT 320,
  height DOUBLE NOT NULL DEFAULT 420,
  z_index INT NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_canvas_nodes_canvas_id (canvas_id),
  INDEX idx_canvas_nodes_canvas_z (canvas_id, z_index),
  INDEX idx_canvas_nodes_task_id (task_id),
  CONSTRAINT fk_canvas_nodes_canvas FOREIGN KEY (canvas_id) REFERENCES user_canvas(id),
  CONSTRAINT fk_canvas_nodes_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
