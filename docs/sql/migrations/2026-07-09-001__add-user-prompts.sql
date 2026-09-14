CREATE TABLE IF NOT EXISTS user_prompt_categories (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  name VARCHAR(100) NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_user_prompt_categories_user_name UNIQUE (user_id, name),
  INDEX idx_user_prompt_categories_user_sort_order (user_id, sort_order, updated_at)
);

CREATE TABLE IF NOT EXISTS user_prompts (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  category_id BIGINT NULL,
  title VARCHAR(255) NOT NULL DEFAULT '',
  content TEXT NOT NULL,
  is_deleted TINYINT(1) NOT NULL DEFAULT 0,
  deleted_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_user_prompts_user_updated (user_id, is_deleted, updated_at),
  INDEX idx_user_prompts_category_id (category_id)
);
