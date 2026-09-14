-- 新增个人邀请奖励体系：用户固定邀请码 + 邀请奖励流水。
-- 回滚思路：确认无需保留数据后，DROP TABLE referral_reward_grants；再 DROP INDEX ux_users_invite_code ON users 并 DROP COLUMN invite_code。

ALTER TABLE users
    ADD COLUMN invite_code VARCHAR(16) NULL AFTER is_whitelisted;

-- 存量用户邀请码由应用启动时的 backfill 生成，确保字符集与代码校验规则一致。

CREATE UNIQUE INDEX ux_users_invite_code ON users (invite_code);

CREATE TABLE IF NOT EXISTS referral_reward_grants (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    referrer_id INTEGER NOT NULL,
    invitee_id INTEGER NOT NULL,
    source_type VARCHAR(20) NOT NULL,
    source_id VARCHAR(64) NOT NULL,
    source_credits INTEGER NOT NULL DEFAULT 0,
    reward_rate INTEGER NOT NULL DEFAULT 15,
    reward_credits INTEGER NOT NULL DEFAULT 0,
    reward_index INTEGER NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY ix_referral_reward_grants_referrer_id (referrer_id),
    KEY ix_referral_reward_grants_invitee_id (invitee_id),
    KEY ix_referral_reward_grants_source_type (source_type),
    KEY ix_referral_reward_grants_source_id (source_id),
    UNIQUE KEY ux_referral_reward_source (source_type, source_id, referrer_id),
    UNIQUE KEY ux_referral_reward_index (referrer_id, invitee_id, reward_index),
    CONSTRAINT fk_referral_reward_referrer_id FOREIGN KEY (referrer_id) REFERENCES users (id),
    CONSTRAINT fk_referral_reward_invitee_id FOREIGN KEY (invitee_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
