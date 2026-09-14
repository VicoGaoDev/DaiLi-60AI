-- Add persistent grouping support for infinite canvas nodes.

CREATE TABLE IF NOT EXISTS canvas_groups (
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

ALTER TABLE canvas_nodes
  ADD COLUMN group_id INT NULL;

CREATE INDEX idx_canvas_nodes_group_id ON canvas_nodes (group_id);

ALTER TABLE canvas_nodes
  ADD CONSTRAINT fk_canvas_nodes_group
  FOREIGN KEY (group_id) REFERENCES canvas_groups(id)
  ON DELETE SET NULL;
