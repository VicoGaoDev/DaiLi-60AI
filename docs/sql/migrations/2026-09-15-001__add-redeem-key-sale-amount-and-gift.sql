-- 影响范围：
-- 1) credit_redeem_keys 增加 sale_amount_fen，支持该批兑换码自定义售价；
-- 2) credit_redeem_keys 增加 is_gift，标记赠送积分码，统计时不计入营业额；
-- 3) 历史兑换码 is_gift 默认为 0，sale_amount_fen 为空，继续按预算单价计算。
--
-- 回滚思路：
-- 1) ALTER TABLE credit_redeem_keys DROP COLUMN is_gift, DROP COLUMN sale_amount_fen;

ALTER TABLE credit_redeem_keys
  ADD COLUMN sale_amount_fen INT NULL COMMENT '单码自定义售价，分；空则按预算单价',
  ADD COLUMN is_gift TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否赠送积分；1 则不计入营业额';
