-- 影响范围：
-- 1) credit_redeem_keys 增加 source / is_locked 字段，用于区分来源与控制删除锁定；
-- 2) 存量兑换码统一补全 source，默认未锁定；
-- 3) credit_logs 增加 credit_type 字段，用于区分个人积分流水与代理池流水；
-- 4) 为既有 agent 用户补齐 type=1 代理积分池账户；
-- 5) 增加代理兑换码后台查询索引。
--
-- 回滚思路：
-- 1) DROP INDEX idx_credit_logs_user_credit_type_created ON credit_logs;
-- 2) DROP INDEX idx_credit_redeem_keys_agent_source_status_used ON credit_redeem_keys;
-- 3) ALTER TABLE credit_logs DROP COLUMN credit_type;
-- 4) ALTER TABLE credit_redeem_keys DROP COLUMN is_locked;
-- 5) ALTER TABLE credit_redeem_keys DROP COLUMN source;

ALTER TABLE credit_redeem_keys
  ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'system' COMMENT '兑换码来源：system 系统发放，agent 代理人发放' AFTER status,
  ADD COLUMN is_locked TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否锁定：1 锁定，0 未锁定' AFTER source;

UPDATE credit_redeem_keys
SET source = 'system'
WHERE source IS NULL OR source = '';

CREATE INDEX idx_credit_redeem_keys_agent_source_status_used
  ON credit_redeem_keys (created_by, source, status, used_at);

ALTER TABLE credit_logs
  ADD COLUMN credit_type INT NOT NULL DEFAULT 0 COMMENT '积分账户类型：0 个人积分，1 代理积分池' AFTER type;

CREATE INDEX idx_credit_logs_user_credit_type_created
  ON credit_logs (user_id, credit_type, created_at);

INSERT INTO user_credits (user_id, type, remain_credit, used_credit, status, expire_time, created_at, updated_at)
SELECT users.id, 1, 0, 0, 1, '2027-12-30 23:59:59', NOW(), NOW()
FROM users
LEFT JOIN user_credits
  ON user_credits.user_id = users.id
 AND user_credits.type = 1
WHERE users.role = 'agent'
  AND user_credits.id IS NULL;
