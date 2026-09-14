-- Add public 16-character project IDs for infinite canvas routes.
-- Existing canvas URLs should use /canvas/{project_id}, not the internal numeric primary key.

ALTER TABLE user_canvas
  ADD COLUMN project_id VARCHAR(16) NULL;

UPDATE user_canvas
SET project_id = SUBSTRING(REPLACE(UUID(), '-', ''), 1, 16)
WHERE project_id IS NULL OR project_id = '';

ALTER TABLE user_canvas
  MODIFY project_id VARCHAR(16) NOT NULL;

CREATE UNIQUE INDEX idx_user_canvas_project_id ON user_canvas (project_id);
