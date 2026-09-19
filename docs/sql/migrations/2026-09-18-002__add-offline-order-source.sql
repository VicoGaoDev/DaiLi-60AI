-- 影响范围：
-- 1) offline_orders 增加 source 字段，用于区分普通线下订单与代理积分池分配流水；
-- 2) 存量数据默认回填为 manual；
-- 3) 为 source 增加查询索引，支持营业额统计与代理人流水筛选。

ALTER TABLE offline_orders
  ADD COLUMN source VARCHAR(30) NOT NULL DEFAULT 'manual' COMMENT '订单来源：manual 普通线下订单，agent_pool_allocate 代理积分池分配' AFTER order_type;

UPDATE offline_orders
SET source = 'manual'
WHERE source IS NULL OR source = '';

CREATE INDEX ix_offline_orders_source
  ON offline_orders (source);
