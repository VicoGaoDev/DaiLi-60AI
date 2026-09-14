-- 新增白名单推广现金返利记账：被推广用户在线购买后按档位记录返利金额，平台不提现。
-- 回滚思路：确认无需保留数据后，DROP TABLE promo_reward_grants。

CREATE TABLE IF NOT EXISTS promo_reward_grants (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    referrer_id INTEGER NOT NULL,
    invitee_id INTEGER NOT NULL,
    promo_code_id INTEGER NULL,
    source_type VARCHAR(20) NOT NULL,
    source_id VARCHAR(64) NOT NULL,
    source_credits INTEGER NOT NULL DEFAULT 0,
    source_amount_fen INTEGER NOT NULL DEFAULT 0,
    reward_rate INTEGER NOT NULL DEFAULT 30,
    reward_amount_fen INTEGER NOT NULL DEFAULT 0,
    reward_index INTEGER NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY ix_promo_reward_grants_referrer_id (referrer_id),
    KEY ix_promo_reward_grants_invitee_id (invitee_id),
    KEY ix_promo_reward_grants_promo_code_id (promo_code_id),
    KEY ix_promo_reward_grants_source_type (source_type),
    KEY ix_promo_reward_grants_source_id (source_id),
    UNIQUE KEY ux_promo_reward_source (source_type, source_id, referrer_id),
    UNIQUE KEY ux_promo_reward_index (referrer_id, invitee_id, reward_index),
    CONSTRAINT fk_promo_reward_referrer_id FOREIGN KEY (referrer_id) REFERENCES users (id),
    CONSTRAINT fk_promo_reward_invitee_id FOREIGN KEY (invitee_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
