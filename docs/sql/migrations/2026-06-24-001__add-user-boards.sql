-- Add user boards and associate generation tasks with a board.
-- Execute once after 2026-06-18-001__manual-schema-migration-baseline.sql.

CREATE TABLE IF NOT EXISTS user_boards (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  name VARCHAR(100) NOT NULL DEFAULT '',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_user_boards_user_id (user_id),
  INDEX idx_user_boards_user_updated_at (user_id, updated_at),
  CONSTRAINT fk_user_boards_user FOREIGN KEY (user_id) REFERENCES users(id)
);

ALTER TABLE tasks
  ADD COLUMN board_id INT NULL;

CREATE INDEX idx_tasks_board_id ON tasks (board_id);
CREATE INDEX idx_tasks_user_board_deleted_created ON tasks (user_id, board_id, is_deleted, created_at);

ALTER TABLE tasks
  ADD CONSTRAINT fk_tasks_board
  FOREIGN KEY (board_id) REFERENCES user_boards(id)
  ON DELETE SET NULL;
