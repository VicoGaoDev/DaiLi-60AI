# web实时任务情况 
select t.business_id,u.username,u.id,t.provider_task_id,t.model,t.reference_images,t.size,t.resolution,t.status,TIMESTAMPDIFF(SECOND, t.created_at, t.updated_at) as run_time,
        TIMESTAMPDIFF(SECOND, t.request_started_at, t.request_finished_at) as request_time,
        t.created_at,t.error_message
    from tasks t
    join users u on t.user_id = u.id
    where t.source = 'web' and t.status = 'failed'
    order by t.created_at desc limit 30;

select * from user_api_key where user_id = 1577;
    
# API实时任务情况 
select t.business_id,t.prompt,u.username,t.model,t.size,t.source,t.status,TIMESTAMPDIFF(SECOND, t.created_at, t.updated_at) as run_time,
        TIMESTAMPDIFF(SECOND, t.request_started_at, t.request_finished_at) as request_time,t.request_started_at, t.request_finished_at,
        t.created_at,t.error_message,t.provider_task_id 
    from tasks t
    join users u on t.user_id = u.id
    order by t.created_at desc limit 50;
    
# API实时任务情况 
select u.username,t.model,t.size,t.resolution,t.status,TIMESTAMPDIFF(SECOND, t.created_at, t.updated_at) as run_time,
        TIMESTAMPDIFF(SECOND, t.request_started_at, t.request_finished_at) as request_time,
        t.created_at,t.error_message 
    from tasks t
    join users u on t.user_id = u.id
    where t.source = 'web' and t.error_message like '%参考图片最多 5 张，当前%'
    order by t.created_at desc limit 100;
    
    
# 最近7天，每天任务数量和消耗积分
SELECT
  DATE(t.created_at) AS stat_date,
  COUNT(*) AS total_task_count,
  COALESCE(
    SUM(
      CASE
        WHEN refund.task_id IS NOT NULL THEN 0
        ELSE t.credit_cost
      END
    ),
    0
  ) AS credits_consumed,
  SUM(CASE WHEN t.status = 'success' THEN 1 ELSE 0 END) AS success_task_count,
  SUM(CASE WHEN t.status = 'failed' THEN 1 ELSE 0 END) AS failed_task_count
FROM tasks t
JOIN users u ON u.id = t.user_id
LEFT JOIN (
  SELECT DISTINCT task_id
  FROM credit_logs
  WHERE task_id IS NOT NULL
    AND type = 'allocate'
    AND description IN ('任务入队失败，返还积分', '任务失败，返还积分')
) refund ON refund.task_id = t.id
WHERE u.is_whitelisted = 0
  AND u.role NOT IN ('admin', 'superadmin')
  AND t.created_at >= DATE_SUB(CURDATE(), INTERVAL 1 DAY)
GROUP BY DATE(t.created_at)
ORDER BY stat_date DESC;

# 查看当天积分兑换码，按积分值分别使用了多少个，以及收入
WITH daily_redeem AS (
  SELECT
    DATE(used_at) AS use_date,
    credit_amount,
    COUNT(*) AS used_count,
    CASE credit_amount
      WHEN 30 THEN 1.45
      WHEN 50 THEN 3.50
      WHEN 70 THEN 2.00
      WHEN 300 THEN 18.50
      WHEN 500 THEN 34.00
      WHEN 1000 THEN 65.00
      WHEN 2000 THEN 120.00
      WHEN 6000 THEN 300.00
      ELSE 0
    END AS unit_price
  FROM credit_redeem_keys
  WHERE used_at >= '2026-06-01 00:00:00'
    AND used_at < '2026-06-02 00:00:00'
  GROUP BY DATE(used_at), credit_amount
)
SELECT
  use_date,
  credit_amount,
  used_count,
  unit_price,
  ROUND(used_count * unit_price, 2) AS daily_income,
  ROUND(SUM(used_count * unit_price) OVER (), 2) AS target_date_total_income
FROM daily_redeem
ORDER BY credit_amount ASC;


# 计算每天的积分兑换对应营业额
SELECT
  DATE(CONVERT_TZ(used_at, '+00:00', '+08:00')) AS beijing_date,
  ROUND(
    SUM(
      CASE credit_amount
        WHEN 30 THEN 2.00
        WHEN 50 THEN 3.50
        WHEN 70 THEN 2.00
        WHEN 300 THEN 18.50
        WHEN 500 THEN 34.00
        WHEN 1000 THEN 65.00
        WHEN 2000 THEN 120.00
        WHEN 6000 THEN 300.00
        ELSE 0
      END
    ),
    2
  ) AS daily_income
FROM credit_redeem_keys
WHERE used_at >= CONVERT_TZ(CURDATE() - INTERVAL 29 DAY, '+00:00', '+00:00')
  AND used_at < CONVERT_TZ(CURDATE() + INTERVAL 1 DAY, '+00:00', '+00:00')
GROUP BY DATE(CONVERT_TZ(used_at, '+00:00', '+08:00'))
ORDER BY beijing_date DESC;


# 每个模型的使用数量
SELECT
  DATE(t.created_at) AS stat_date,
  COALESCE(NULLIF(t.model, ''), '未设置') AS model,
  COUNT(*) AS success_charged_task_count,
  COALESCE(SUM(t.credit_cost), 0) AS credits_consumed
FROM tasks t
JOIN users u ON u.id = t.user_id
WHERE u.is_whitelisted = 0
  AND t.status = 'success'
  AND t.credit_cost > 0
  AND u.role NOT IN ('admin', 'superadmin')
  AND t.created_at >= DATE_SUB(CURDATE(), INTERVAL 1 DAY)
GROUP BY DATE(t.created_at), COALESCE(NULLIF(t.model, ''), '未设置')
ORDER BY stat_date DESC, success_charged_task_count DESC;


select u.username,k.api_key from user_api_key as k
    left join users as u on k.user_id = u.id;
select * from users WHERE id = 259;
select * from users order by created_at desc limit 50;


# 复购的用户
SELECT
  u.id AS user_id,
  u.username,
  u.email,
  COUNT(*) AS redeem_count,
  SUM(rk.credit_amount) AS total_redeem_credits,
  MIN(rk.used_at) AS first_redeem_at,
  MAX(rk.used_at) AS last_redeem_at
FROM credit_redeem_keys rk
JOIN users u ON u.id = rk.used_by_user_id
WHERE rk.used_at IS NOT NULL
  AND rk.credit_amount > 200
  AND u.is_whitelisted = 0
  AND u.role NOT IN ('admin', 'superadmin')
GROUP BY u.id, u.username, u.email
HAVING COUNT(*) >= 2
ORDER BY redeem_count DESC, total_redeem_credits DESC;


select * from payment_orders;
select * from user_api_key order by created_at desc limit 50; 
select * from users where id = 579;


# 统计所有用户剩余积分总和的sql
SELECT COALESCE(SUM(uc.remain_credit), 0) AS total_remaining_credits
FROM user_credits uc
JOIN users u ON u.id = uc.user_id
WHERE uc.type = 0
  AND uc.status = 1
  AND u.is_whitelisted = 0
  AND u.role NOT IN ('admin', 'superadmin');

# user_boards
select
    b.created_at,
    u.username,
    b.id as board_id,
    b.name,
    count(t.id) as task_count
from user_boards b
join users u on b.user_id = u.id
left join tasks t
    on t.board_id = b.id
   and t.is_deleted = 0
group by b.id, b.created_at, u.username, b.name
order by b.created_at desc
limit 30;

# 用户canvas情况查看，节点
select
    c.created_at,
    u.username,
    c.project_id,
    c.name,
    count(n.id) as node_count
from user_canvas c
join users u on c.user_id = u.id
left join canvas_nodes n on n.canvas_id = c.id
group by c.id, c.created_at, u.username, c.project_id, c.name
order by c.created_at desc
limit 30;
    
select * from user_api_key order by created_at desc;

select * from user_prompts order by created_at desc limit 50;


select * FROM user_assets where user_id = 895;
select count(*) FROM user_assets where user_id = 895 and is_deleted = 1;

select * from users where business_id = 'aef23818897343ae83e5562f741af907';


# 统计2000分以上用户信息
SELECT
  u.created_at AS register_at,
  u.username,
  u.email,
  COALESCE(p.purchase_count, 0) AS online_purchase_count,
  COALESCE(r.redeem_count, 0) AS redeem_count,
  COALESCE(p.purchase_credits, 0) + COALESCE(r.redeem_credits, 0) AS total_credits
FROM users u
LEFT JOIN (
  SELECT
    user_id,
    COUNT(*) AS purchase_count,
    COALESCE(SUM(credits), 0) AS purchase_credits
  FROM payment_orders
  WHERE status IN ('paid', 'credited')
    AND credited_at IS NOT NULL
  GROUP BY user_id
) p ON p.user_id = u.id
LEFT JOIN (
  SELECT
    used_by_user_id AS user_id,
    COUNT(*) AS redeem_count,
    COALESCE(SUM(credit_amount), 0) AS redeem_credits
  FROM credit_redeem_keys
  WHERE used_at IS NOT NULL
    AND used_by_user_id IS NOT NULL
  GROUP BY used_by_user_id
) r ON r.user_id = u.id
WHERE u.is_whitelisted = 0
  AND u.role NOT IN ('admin', 'superadmin')
  AND COALESCE(p.purchase_credits, 0) + COALESCE(r.redeem_credits, 0) >= 2000
ORDER BY total_credits DESC;


# 视频任务
select user_id,status,prompt,error_message,is_deleted from video_tasks order by created_at desc limit 10;


select * from referral_reward_grants order by created_at desc limit 100;

select * from user_prompts;
select count(*) from user_assets;

# 提示词优化任务
select p.created_at,u.username,p.original_prompt,p.optimized_prompt 
    from prompt_optimize_tasks p
    join users u on p.user_id = u.id
    order by p.created_at desc limit 50;

# 对话消息
select * from chat_messages order by created_at desc limit 50;

# 对话session
select c.created_at,u.username
    from chat_sessions c
    join users u on c.user_id = u.id
    order by c.created_at desc limit 50;



# 场景使用量统计
SELECT
  DATE(t.created_at) AS stat_date,
  t.model,
  COUNT(*) AS usage_count,
  COALESCE(SUM(t.credit_cost), 0) AS credits_consumed
FROM tasks t
JOIN users u ON u.id = t.user_id
WHERE t.model = 'banana2_edit'
  AND t.status = 'success'
  AND t.credit_cost > 0
  AND u.is_whitelisted = 0
  AND u.role NOT IN ('admin', 'superadmin')
  AND t.created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
  AND t.created_at < DATE_ADD(CURDATE(), INTERVAL 1 DAY)
GROUP BY DATE(t.created_at), t.model
ORDER BY stat_date DESC;

select * from user_credits ORDER BY created_at DESC limit 10;

