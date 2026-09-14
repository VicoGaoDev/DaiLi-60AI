-- 影响范围：
-- 1) 新增 AI 对话三方接口配置、场景绑定、会话与消息表；
-- 2) chat_sessions.session_id：对外公开 16 位 ID（yymmddhhmmss + 4 位随机字母数字）；
-- 3) chat_external_api_scene_bindings.context_message_limit 默认 10；
-- 4) chat_external_api_scene_bindings.starter_prompts_json：场景内置引导问题（JSON 数组，最多 4 条）；
-- 5) 不修改既有生图/视频/提示词优化表。
--
-- 回滚思路：
-- 1) 若仅执行了本脚本且尚未发布依赖代码，可按依赖顺序删除四张新表。

CREATE TABLE IF NOT EXISTS chat_external_api_configs (
  id INT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL UNIQUE,
  description VARCHAR(255) NOT NULL DEFAULT '',
  group_name VARCHAR(100) NOT NULL DEFAULT '默认',
  request_url VARCHAR(500) NOT NULL DEFAULT '',
  request_format VARCHAR(20) NOT NULL DEFAULT 'json',
  headers_json TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  response_json TEXT NOT NULL,
  result_text_field VARCHAR(255) NOT NULL DEFAULT '',
  result_error_field VARCHAR(255) NOT NULL DEFAULT '',
  call_mode VARCHAR(20) NOT NULL DEFAULT 'sync',
  submit_success_statuses_json TEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'enabled',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_external_api_scene_bindings (
  id INT PRIMARY KEY AUTO_INCREMENT,
  scene_key VARCHAR(50) NOT NULL UNIQUE,
  is_deleted BOOLEAN NOT NULL DEFAULT 0,
  scene_label VARCHAR(100) NOT NULL DEFAULT '',
  scene_description VARCHAR(255) NOT NULL DEFAULT '',
  sort_order INT NOT NULL DEFAULT 0,
  status VARCHAR(20) NOT NULL DEFAULT 'enabled',
  api_config_id INT NULL,
  backup_api_config_id INT NULL,
  display_name VARCHAR(100) NOT NULL DEFAULT '',
  subtitle VARCHAR(255) NOT NULL DEFAULT '',
  credit_cost INT NOT NULL DEFAULT 0,
  system_prompt TEXT NOT NULL,
  context_message_limit INT NOT NULL DEFAULT 10,
  opening_greeting VARCHAR(1000) NOT NULL DEFAULT '',
  starter_prompts_json TEXT NOT NULL,
  updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_chat_scene_bindings_status_sort (status, sort_order, scene_key),
  CONSTRAINT fk_chat_scene_api_config FOREIGN KEY (api_config_id) REFERENCES chat_external_api_configs(id),
  CONSTRAINT fk_chat_scene_backup_api_config FOREIGN KEY (backup_api_config_id) REFERENCES chat_external_api_configs(id)
);

CREATE TABLE IF NOT EXISTS chat_sessions (
  id INT PRIMARY KEY AUTO_INCREMENT,
  session_id VARCHAR(16) NOT NULL UNIQUE,
  user_id INT NOT NULL,
  title VARCHAR(100) NOT NULL DEFAULT '',
  model VARCHAR(50) NOT NULL DEFAULT '',
  is_deleted BOOLEAN NOT NULL DEFAULT 0,
  last_message_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_chat_sessions_user_updated (user_id, is_deleted, updated_at),
  KEY idx_chat_sessions_user_last_message (user_id, is_deleted, last_message_at),
  CONSTRAINT fk_chat_sessions_user FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id INT PRIMARY KEY AUTO_INCREMENT,
  session_id INT NOT NULL,
  reply_to_message_id INT NULL,
  role VARCHAR(20) NOT NULL DEFAULT 'user',
  content TEXT NOT NULL,
  model VARCHAR(50) NOT NULL DEFAULT '',
  client_message_id VARCHAR(64) NULL,
  credit_cost INT NOT NULL DEFAULT 0,
  status VARCHAR(20) NOT NULL DEFAULT 'success',
  error_message VARCHAR(2000) NOT NULL DEFAULT '',
  provider_api_config_id INT NULL,
  used_fallback_api BOOLEAN NOT NULL DEFAULT 0,
  provider_response_preview TEXT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_chat_messages_session_id (session_id, id),
  KEY idx_chat_messages_reply_to (reply_to_message_id),
  UNIQUE KEY uq_chat_messages_session_client (session_id, client_message_id),
  CONSTRAINT fk_chat_messages_session FOREIGN KEY (session_id) REFERENCES chat_sessions(id),
  CONSTRAINT fk_chat_messages_reply_to FOREIGN KEY (reply_to_message_id) REFERENCES chat_messages(id)
);

-- 对已有空配置场景写入一组默认内置问题
UPDATE chat_external_api_scene_bindings
SET starter_prompts_json = '[{"tag":"生图","text":"怎么样才能让 AI 生图更准确、更好看？有哪些关键方法和常见坑？"},{"tag":"生图","text":"我想做电商产品图，白底运动鞋怎么拍出质感和卖点？"},{"tag":"生图","text":"有一张人像照片，想改成赛博朋克风格，该怎么操作更稳？"},{"tag":"生视频","text":"怎么样才能让 AI 生视频更稳、更自然？有哪些关键方法和常见坑？"}]'
WHERE starter_prompts_json IS NULL OR starter_prompts_json = '' OR starter_prompts_json = '[]';
