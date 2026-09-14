-- Add ticket-style feedback messages and per-side read positions.

ALTER TABLE feedback
  ADD COLUMN last_message_at DATETIME NULL,
  ADD COLUMN user_last_read_at DATETIME NULL,
  ADD COLUMN admin_last_read_at DATETIME NULL;

UPDATE feedback
SET last_message_at = COALESCE(last_message_at, created_at),
    user_last_read_at = COALESCE(user_last_read_at, created_at)
WHERE last_message_at IS NULL OR user_last_read_at IS NULL;

CREATE TABLE IF NOT EXISTS feedback_messages (
  id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  business_id VARCHAR(32) NOT NULL,
  feedback_id INT NOT NULL,
  sender_role VARCHAR(20) NOT NULL DEFAULT 'user',
  sender_id INT NULL,
  content TEXT NOT NULL,
  attachments_json TEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY ix_feedback_messages_business_id (business_id),
  KEY ix_feedback_messages_feedback_id (feedback_id),
  KEY ix_feedback_messages_sender_role (sender_role),
  KEY ix_feedback_messages_sender_id (sender_id),
  KEY ix_feedback_messages_created_at (created_at),
  KEY ix_feedback_messages_feedback_created (feedback_id, created_at),
  CONSTRAINT fk_feedback_messages_feedback_id FOREIGN KEY (feedback_id) REFERENCES feedback(id) ON DELETE CASCADE,
  CONSTRAINT fk_feedback_messages_sender_id FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO feedback_messages (
  business_id,
  feedback_id,
  sender_role,
  sender_id,
  content,
  attachments_json,
  created_at
)
SELECT
  LOWER(REPLACE(UUID(), '-', '')),
  f.id,
  'user',
  f.user_id,
  COALESCE(f.content, ''),
  COALESCE(NULLIF(f.attachments_json, ''), '[]'),
  COALESCE(f.created_at, CURRENT_TIMESTAMP)
FROM feedback f
LEFT JOIN feedback_messages m ON m.feedback_id = f.id
WHERE m.id IS NULL;

CREATE INDEX ix_feedback_last_message_at ON feedback (last_message_at);
