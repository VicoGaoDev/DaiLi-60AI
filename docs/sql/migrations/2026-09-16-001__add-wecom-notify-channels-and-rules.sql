-- 影响范围：
-- 1) 新增 wecom_webhook_channels，保存企业微信群机器人通道；
-- 2) 新增 wecom_notify_rules，保存触发场景、条件、可编辑模版与目标通道；
-- 3) 首次打开后台且通道/规则表都为空时，按环境变量回填默认通道和规则。
--
-- 回滚思路：
-- 1) DROP TABLE wecom_notify_rules;
-- 2) DROP TABLE wecom_webhook_channels;

CREATE TABLE IF NOT EXISTS wecom_webhook_channels (
  id INT NOT NULL AUTO_INCREMENT,
  business_id VARCHAR(32) NOT NULL,
  name VARCHAR(50) NOT NULL,
  webhook_url VARCHAR(500) NOT NULL DEFAULT '',
  is_enabled TINYINT(1) NOT NULL DEFAULT 0,
  remark VARCHAR(200) NOT NULL DEFAULT '',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_wecom_webhook_channels_business_id (business_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS wecom_notify_rules (
  id INT NOT NULL AUTO_INCREMENT,
  business_id VARCHAR(32) NOT NULL,
  channel_id INT NOT NULL,
  event_key VARCHAR(50) NOT NULL,
  name VARCHAR(80) NOT NULL,
  is_enabled TINYINT(1) NOT NULL DEFAULT 1,
  conditions_json TEXT NOT NULL,
  template_markdown TEXT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_wecom_notify_rules_business_id (business_id),
  KEY ix_wecom_notify_rules_channel_id (channel_id),
  KEY ix_wecom_notify_rules_event_key (event_key),
  CONSTRAINT fk_wecom_notify_rules_channel FOREIGN KEY (channel_id) REFERENCES wecom_webhook_channels (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
