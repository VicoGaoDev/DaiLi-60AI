-- Production rollout SQL for Infinite Canvas.
--
-- Execute this file ONCE before deploying code that exposes `/canvas`.
-- This is a clean one-time migration for production environments that have not
-- applied the split canvas migrations below:
--   - 2026-06-26-001__add-user-canvas.sql
--   - 2026-06-29-001__add-canvas-project-id.sql
--   - 2026-06-29-002__add-canvas-free-nodes.sql
--
-- Before execution:
--   1. Back up production database.
--   2. Confirm the selected database: SELECT DATABASE();
--   3. Confirm these objects do not already exist:
--      SHOW TABLES LIKE 'user_canvas';
--      SHOW TABLES LIKE 'canvas_groups';
--      SHOW TABLES LIKE 'canvas_nodes';
--      SHOW TABLES LIKE 'canvas_edges';
--      SHOW COLUMNS FROM tasks LIKE 'canvas_id';

CREATE TABLE user_canvas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  project_id VARCHAR(16) NOT NULL,
  user_id INT NOT NULL,
  name VARCHAR(100) NOT NULL DEFAULT '',
  viewport_x DOUBLE NOT NULL DEFAULT 0,
  viewport_y DOUBLE NOT NULL DEFAULT 0,
  zoom DOUBLE NOT NULL DEFAULT 0.5,
  is_deleted BOOLEAN NOT NULL DEFAULT 0,
  deleted_at DATETIME NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY idx_user_canvas_project_id (project_id),
  INDEX idx_user_canvas_user_id (user_id),
  INDEX idx_user_canvas_user_updated_at (user_id, updated_at),
  INDEX idx_user_canvas_user_deleted_updated (user_id, is_deleted, updated_at),
  CONSTRAINT fk_user_canvas_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE tasks
  ADD COLUMN canvas_id INT NULL;

CREATE INDEX idx_tasks_canvas_id ON tasks (canvas_id);
CREATE INDEX idx_tasks_user_canvas_deleted_created ON tasks (user_id, canvas_id, is_deleted, created_at);

ALTER TABLE tasks
  ADD CONSTRAINT fk_tasks_canvas
  FOREIGN KEY (canvas_id) REFERENCES user_canvas(id)
  ON DELETE SET NULL;

CREATE TABLE canvas_groups (
  id INT AUTO_INCREMENT PRIMARY KEY,
  canvas_id INT NOT NULL,
  name VARCHAR(100) NOT NULL DEFAULT '',
  color VARCHAR(32) NOT NULL DEFAULT '#ffab27',
  x DOUBLE NOT NULL DEFAULT 0,
  y DOUBLE NOT NULL DEFAULT 0,
  width DOUBLE NOT NULL DEFAULT 320,
  height DOUBLE NOT NULL DEFAULT 220,
  z_index INT NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_canvas_groups_canvas_id (canvas_id),
  INDEX idx_canvas_groups_canvas_z (canvas_id, z_index),
  CONSTRAINT fk_canvas_groups_canvas FOREIGN KEY (canvas_id) REFERENCES user_canvas(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE canvas_nodes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  canvas_id INT NOT NULL,
  group_id INT NULL,
  task_id INT NULL,
  node_type VARCHAR(20) NOT NULL DEFAULT 'task',
  content VARCHAR(5000) NOT NULL DEFAULT '',
  image_url VARCHAR(1000) NOT NULL DEFAULT '',
  x DOUBLE NOT NULL DEFAULT 0,
  y DOUBLE NOT NULL DEFAULT 0,
  width DOUBLE NOT NULL DEFAULT 320,
  height DOUBLE NOT NULL DEFAULT 420,
  z_index INT NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_canvas_nodes_canvas_id (canvas_id),
  INDEX idx_canvas_nodes_canvas_z (canvas_id, z_index),
  INDEX idx_canvas_nodes_group_id (group_id),
  INDEX idx_canvas_nodes_task_id (task_id),
  CONSTRAINT fk_canvas_nodes_canvas FOREIGN KEY (canvas_id) REFERENCES user_canvas(id),
  CONSTRAINT fk_canvas_nodes_group FOREIGN KEY (group_id) REFERENCES canvas_groups(id) ON DELETE SET NULL,
  CONSTRAINT fk_canvas_nodes_task FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE canvas_edges (
  id INT AUTO_INCREMENT PRIMARY KEY,
  canvas_id INT NOT NULL,
  source_node_id INT NOT NULL,
  target_node_id INT NOT NULL,
  edge_type VARCHAR(20) NOT NULL DEFAULT 'reference',
  source_anchor VARCHAR(10) NOT NULL DEFAULT 'auto',
  target_anchor VARCHAR(10) NOT NULL DEFAULT 'auto',
  is_collapsed BOOLEAN NOT NULL DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_canvas_edges_canvas_id (canvas_id),
  INDEX idx_canvas_edges_source_node_id (source_node_id),
  INDEX idx_canvas_edges_target_node_id (target_node_id),
  CONSTRAINT fk_canvas_edges_canvas FOREIGN KEY (canvas_id) REFERENCES user_canvas(id) ON DELETE CASCADE,
  CONSTRAINT fk_canvas_edges_source_node FOREIGN KEY (source_node_id) REFERENCES canvas_nodes(id) ON DELETE CASCADE,
  CONSTRAINT fk_canvas_edges_target_node FOREIGN KEY (target_node_id) REFERENCES canvas_nodes(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
