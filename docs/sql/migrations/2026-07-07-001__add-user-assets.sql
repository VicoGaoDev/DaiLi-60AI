CREATE TABLE IF NOT EXISTS user_asset_categories (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  name VARCHAR(100) NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT uq_user_asset_categories_user_name UNIQUE (user_id, name),
  INDEX idx_user_asset_categories_user_sort_order (user_id, sort_order, updated_at)
);

CREATE TABLE IF NOT EXISTS user_assets (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  category_id BIGINT NULL,
  file_name VARCHAR(255) NOT NULL DEFAULT '',
  object_key VARCHAR(500) NOT NULL DEFAULT '',
  url VARCHAR(1000) NOT NULL DEFAULT '',
  thumbnail_url VARCHAR(1000) NOT NULL DEFAULT '',
  mime_type VARCHAR(100) NOT NULL DEFAULT '',
  file_size INT NOT NULL DEFAULT 0,
  width INT NULL,
  height INT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  is_deleted TINYINT(1) NOT NULL DEFAULT 0,
  deleted_at DATETIME NULL,
  completed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_user_assets_user_created (user_id, created_at),
  INDEX idx_user_assets_category_id (category_id),
  INDEX idx_user_assets_user_deleted_status (user_id, is_deleted, status, completed_at)
);
