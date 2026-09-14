-- 影响范围：
-- 1) users 增加 phone / phone_verified，支持手机号注册、短信登录和账号互绑；
-- 2) users 增加 password_set，区分已设密与待设密；
-- 3) 不改已有邮箱账号数据，存量用户 password_set 默认为 1。
--
-- 回滚思路：
-- 1) DROP INDEX ux_users_phone ON users;
-- 2) ALTER TABLE users DROP COLUMN password_set, DROP COLUMN phone_verified, DROP COLUMN phone;

ALTER TABLE users
  ADD COLUMN phone VARCHAR(20) NULL COMMENT '手机号，仅数字，如 13800138000',
  ADD COLUMN phone_verified TINYINT(1) NOT NULL DEFAULT 0,
  ADD COLUMN password_set TINYINT(1) NOT NULL DEFAULT 1;

CREATE UNIQUE INDEX ux_users_phone ON users (phone);
