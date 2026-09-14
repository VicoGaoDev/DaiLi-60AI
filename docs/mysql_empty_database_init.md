# 空库一键初始化（MySQL）

在**无任何表**的数据库中执行以下脚本，创建与 `backend/app/models` 一致的结构，并插入默认管理员账号。

- 库 / 连接字符集请使用 `utf8mb4`（例如连接串加 `?charset=utf8mb4`）。
- `external_api_scene_bindings` 中参数类 `TEXT` 字段在 MySQL 中不设默认值（`TEXT`/`BLOB` 在多数配置下不能带 `DEFAULT`），由应用层写入；与 ORM 的 Python 侧默认值行为一致。
- 若已由应用 `DB_AUTO_CREATE_TABLES` 建表，请勿重复执行建表；仅需按需插入 `users` 或改用 `DB_RUN_SEED`。
- 首次登录后请立即修改默认密码。
- 当前版本的“剩余积分余额”不再存储在 `users` 表，而是存储在 `user_credits` 表，默认积分类型为 `type = 0`。
- `tasks.created_at` 表示任务记录创建时间。
- `tasks.enqueued_at` 表示任务成功进入分发/入队流程的时间，可用于计算排队耗时。
- `tasks.request_started_at` 表示任务首次真实发起第三方接口请求的时间。
- `tasks.request_finished_at` 表示任务最近一次第三方接口请求返回的时间。
- `tasks.updated_at` 表示任务最近一次状态或内容更新的时间；任务完成后可结合 `created_at` 估算总耗时。

## 关键字段说明

下面只列出后续排查问题、查任务链路、核对配置时最常用的字段语义。

### `users`

- `id`: 用户主键。
- `business_id`: 对外业务 ID，32 位十六进制字符串；API、JWT、管理端与客户端统一使用这个字段，不直接暴露内部整型主键。
- `username`: 登录用户名；当前库中允许重复用户名历史数据，因此登录时更建议优先使用邮箱。
- `email`: 唯一邮箱，可为空。
- `email_verified`: 邮箱是否已验证。
- `role`: 角色，常见值为 `user`、`admin`、`superadmin`。
- `status`: 账号状态，常见值为 `active`、`disabled`。
- `is_whitelisted`: 是否白名单用户。
- `invite_code`: 个人固定邀请码，格式为 `Uxxxxxxx`，用于普通用户邀请奖励计划。
- `referrer_id`: 推荐人内部用户 ID；当新用户使用个人邀请码或推广码注册时写入。
- `used_promo_code_id`: 注册时使用的推广码记录 ID；可用于追踪具体渠道来源。
- `created_at` / `updated_at`: 用户创建时间、最后更新时间。

### `user_promo_codes`

- `id`: 推广码主键。
- `user_id`: 推广码归属白名单用户。
- `code`: 推广码字符串，唯一。
- `platform_name`: 推广渠道/平台名称，用于区分来源。
- `status`: 推广码状态，当前常见值为 `enabled`、`disabled`。
- `created_at` / `updated_at`: 创建时间、最后更新时间。

### `referral_reward_grants`

- `referrer_id`: 获得邀请奖励的邀请人。
- `invitee_id`: 触发奖励的被邀请用户。
- `source_type`: 奖励来源，当前为 `payment` 或 `redeem`。
- `source_id`: 来源标识，在线支付为订单号，兑换码为兑换码字符串。
- `source_credits`: 被邀请用户本次到账积分。
- `reward_rate`: 奖励比例，默认 `15` 表示 15%。
- `reward_credits`: 实际发放给邀请人的奖励积分。
- `reward_index`: 该被邀请用户触发的第几次奖励，最多记录到 3。

### `promo_reward_grants`

- `referrer_id`: 获得推广现金返利记账的白名单推广人。
- `invitee_id`: 通过推广码注册并触发返利的用户。
- `promo_code_id`: 注册时使用的推广码 ID。
- `source_type`: 当前仅为 `payment`。
- `source_id`: 在线支付订单号。
- `source_credits`: 被推广用户本次到账积分。
- `source_amount_fen`: 订单金额（分）。
- `reward_rate`: 返利比例，第 1–2 单为 `30`，第 3–5 单为 `15`。
- `reward_amount_fen`: 记账返利金额（分）；平台不支持提现。
- `reward_index`: 该被推广用户触发的第几次返利，最多记录到 5。

### `user_credits`

- `id`: 积分账户主键。
- `user_id`: 归属用户。
- `type`: 积分类型；当前默认使用 `0`，便于后续扩展其他余额类型。
- `remain_credit`: 当前剩余积分。
- `used_credit`: 已使用积分累计值；历史数据可按 `credit_logs` 中 `type = 'consume'` 的消费流水聚合回填。
- `status`: 积分账户状态；`1` 表示可用，`0` 表示不可用，默认值为 `1`。
- `expire_time`: 积分过期时间；当前默认值为 `2027-12-30 23:59:59`。
- `created_at` / `updated_at`: 账户创建时间、最后更新时间。
- 使用联合唯一约束 `(user_id, type)` 保证同一用户同一积分类型只有一条余额记录。

### `tasks`

- `id`: 任务内部主键，仅用于数据库内部关联与排障。
- `business_id`: 任务对外业务 ID，32 位十六进制字符串；任务创建响应、轮询接口、历史展示和日志追踪统一使用该字段。
- `user_id`: 发起任务的用户。
- `model`: 生成所用模型或场景模型标识。
- `source`: 任务来源，当前默认 `web`；可用于区分不同客户端或入口。
- `mode`: 任务模式，当前主要为 `generate` 或 `inpaint`。
- `prompt`: 任务提示词。
- `num_images`: 任务声明的图片数量；当前实际生成链路里通常按单图子任务落库。
- `size`: 宽高比，例如 `1:1`、`3:4`。
- `resolution`: 分辨率档位，例如 `2K`、`4K`。
- `custom_size`: 自定义尺寸文本。
- `reference_image`: 单张参考图地址；兼容旧链路或单图场景。
- `reference_images`: 参考图列表，JSON 字符串形式存储。
- `source_image`: 图编辑原图地址。
- `mask_image`: 图编辑蒙版地址。
- `board_id`: 所属历史分类；为空表示默认分类或未分类。
- `canvas_id`: 所属无限画布内部 ID；为空表示普通生图/历史任务。
- `credit_cost`: 单任务积分消耗。
- `status`: 任务状态，常见值为 `pending`、`queued`、`processing`、`success`、`failed`。
- `error_message`: 失败原因或最近一次错误信息。
- `is_deleted`: 是否逻辑删除；用户删除历史任务时会置为 `1`，但后台统计口径通常仍保留这类任务。
- `created_at`: 任务记录写入数据库时间。
- `enqueued_at`: 任务成功进入分发/入队流程时间。
- `request_started_at`: 任务首次真实发起第三方接口请求时间。
- `request_finished_at`: 任务最近一次第三方接口请求返回时间。
- `updated_at`: 任务最后一次状态更新时间；成功或失败后会更新。

### `user_canvas`

- `id`: 画布内部主键。
- `project_id`: 16 位字母数字公开 ID，用于 `/canvas/:projectId` 路由，不对外暴露内部自增主键。
- `user_id`: 画布归属用户。
- `name`: 画布名称。
- `viewport_x` / `viewport_y` / `zoom`: 用户最后保存的画布视口位置与缩放比例。
- `is_deleted`: 是否逻辑删除。
- `deleted_at`: 逻辑删除时间。
- `created_at` / `updated_at`: 创建时间、最后更新时间。

### `user_boards`

- `id`: 历史分类内部主键。
- `user_id`: 分类归属用户。
- `name`: 分类名称。
- `created_at` / `updated_at`: 创建时间、最后更新时间。

### `canvas_groups`

- `id`: 画布分组内部主键。
- `canvas_id`: 所属画布。
- `name`: 分组名称。
- `color`: 分组背景/边框主题色。
- `x` / `y`: 分组框在画布世界坐标中的位置。
- `width` / `height`: 分组框尺寸。
- `z_index`: 分组层级。
- `created_at` / `updated_at`: 创建时间、最后更新时间。

### `canvas_nodes`

- `id`: 节点内部主键。
- `canvas_id`: 所属画布。
- `group_id`: 所属画布分组；为空表示未分组。
- `task_id`: 关联任务；任务节点有值，自由文本节点和上传图片节点为空。
- `node_type`: 节点类型，当前常见为 `task`、`text`、`image`。
- `content`: 文本节点内容。
- `image_url`: 上传图片节点地址。
- `x` / `y`: 节点在画布世界坐标中的位置。
- `width` / `height`: 节点尺寸。
- `z_index`: 节点层级。
- `created_at` / `updated_at`: 创建时间、最后更新时间。

### `canvas_edges`

- `id`: 连线内部主键。
- `canvas_id`: 所属画布。
- `source_node_id` / `target_node_id`: 起点和终点节点。
- `edge_type`: 连线类型，当前默认 `reference`。
- `source_anchor` / `target_anchor`: 连线锚点，当前默认 `auto`。
- `is_collapsed`: 是否折叠。
- `created_at` / `updated_at`: 创建时间、最后更新时间。

### `images`

- `id`: 图片主键。
- `task_id`: 所属任务。
- `image_url`: 最终图片地址。
- `preview_url`: 预览图地址；在最终结果落存储前可能暂时有值。
- `image_format`: 图片格式，例如 `png`、`jpeg`。
- `image_size_bytes`: 图片大小，单位字节。
- `status`: 图片状态，常见值为 `pending`、`success`、`failed`。
- `error_message`: 单张图片失败原因。
- `is_deleted`: 是否逻辑删除。
- `deleted_at`: 逻辑删除时间。
- `created_at`: 图片记录创建时间。

### `credit_logs`

- `id`: 积分流水主键。
- `user_id`: 积分归属用户。
- `amount`: 积分变化量；负数通常表示消耗，正数通常表示返还或发放。
- `type`: 流水类型，当前常见为 `consume`、`allocate`。
- `description`: 流水说明。
- `operator_id`: 操作人；管理员手工加减积分时会用到。
- `task_id`: 关联任务；任务消费和返还时很关键。
- `created_at`: 流水创建时间。

### `credit_redeem_keys`

- `id`: 兑换码主键。
- `redeem_key`: 16 位兑换码，唯一。
- `credit_amount`: 该兑换码可兑换的积分值。
- `batch_no`: 批次号；同一批生成的兑换码共享同一个批次号。
- `status`: 兑换码状态，当前常见值为 `enabled`、`disabled`。
- `created_by`: 生成人；通常为管理员用户 ID。
- `used_by_user_id`: 使用人；兑换成功后写入。
- `used_at`: 兑换成功时间；为空表示尚未使用。
- `created_at` / `updated_at`: 创建时间、最后更新时间。

### `payment_orders`

- `order_no`: 业务订单号，唯一。
- `user_id`: 下单用户。
- `plan_key`: 套餐标识。
- `subject`: 支付展示标题。
- `amount_fen`: 实付金额，单位分。
- `credits`: 支付成功后应到账的积分数。
- `status`: 订单状态，常见值为 `created`、`pending_pay`、`paid`、`credited`、`closed`、`failed`。
- `out_trade_no`: 传给支付宝的商户订单号，当前与 `order_no` 保持一致。
- `alipay_trade_no`: 支付宝交易号，支付成功后写入。
- `buyer_id`: 支付宝买家标识，可为空字符串。
- `trade_status`: 支付宝回调中的交易状态。
- `notify_payload` / `return_payload`: 回调与回跳原始参数，便于排障。
- `paid_at` / `credited_at`: 支付完成时间、积分到账时间。
- `closed_at` / `failed_at`: 关闭或失败时间。
- `created_at` / `updated_at`: 创建时间、最后更新时间。

### `offline_orders`

- `business_id`: 线下订单对外业务 ID，32 位十六进制字符串。
- `user_id`: 绑定的用户。
- `order_type`: 线下订单类型，当前支持 `purchase`（购入）和 `refund`（退款）。
- `credit_amount`: 线下订单对应积分数。
- `amount_fen`: 订单金额，单位为分；前端按人民币元输入，后端换算后按分存储。
- `remark`: 备注。
- `created_by`: 录入管理员用户 ID。
- `created_at` / `updated_at`: 创建时间、最后更新时间。

### `prompt_history`

- `user_id`: 提示词归属用户。
- `prompt`: 历史提示词。
- `mode`: 对应任务模式。
- `source_image`: 图编辑场景关联原图。
- `created_at`: 记录时间。

### `templates`

- `prompt`: 模板提示词。
- `model`: 模板默认模型。
- `reference_images`: 模板参考图列表，文本形式存储。
- `size` / `resolution` / `custom_size`: 模板默认尺寸参数。
- `num_images`: 模板默认生成数量。
- `result_image`: 模板结果图。
- `sort_order`: 模板排序。
- `created_at` / `updated_at`: 模板创建时间、更新时间。

### `template_tags`

- `name`: 标签名称，唯一。
- `created_at`: 标签创建时间。

### `template_tag_relations`

- `template_id`: 模板 ID。
- `tag_id`: 标签 ID。
- 使用联合主键 `(template_id, tag_id)` 保证同一模板不会重复绑定同一标签。

### `api_keys`

- `key`: 站点通用配置项中的主 Key。
- `tongyi_key`: 通义相关密钥。
- `contact_qr_image`: 联系二维码图片地址。
- `cos_secret_id` / `cos_secret_key`: 腾讯云 COS 凭证。
- `cos_bucket` / `cos_region` / `cos_upload_domain` / `cos_public_base_url`: COS 存储配置。
- `announcement_enabled` / `announcement_content` / `announcement_updated_at`: 公告配置。
- `updated_at`: 配置最后更新时间。

### `user_api_key`

- `user_id`: API Key 所属用户。
- `subs_type`: 订阅/套餐类型预留字段。
- `expire_time`: 过期时间，允许为空；为空表示永不过期。
- `api_key`: 用户实际调用 Key，格式为 `sk-` + 32 位大小写字母数字。
- `key_name`: 用户可编辑的 Key 名称。
- `status`: 是否可用，常见为 `enabled` / `disabled`。
- `is_delete`: 软删除标记。
- `created_at` / `updated_at`: 创建时间、更新时间。

### `external_api_configs`

- `name`: 配置名称，唯一。
- `description`: 配置说明。
- `group_name`: 配置分组。
- `model_key`: 模型标识。
- `model_label` / `model_description`: 前台展示文案。
- `sort_order`: 配置排序。
- `hide_resolution`: 是否在前端隐藏分辨率参数。
- `request_url`: 实际调用地址。
- `request_format`: 请求发送格式，当前支持 `json` 与 `multipart`；图编辑等文件上传型接口建议显式配置。
- `headers_json`: 请求头模板。
- `payload_json`: 请求体模板。
- `response_json`: 响应示例或结构模板。
- `result_base64_field`: 响应中图片 base64 的提取路径。
- `supports_generation` / `supports_inpaint` / `supports_prompt_reverse`: 功能支持矩阵。
- `is_active_generation` / `is_active_inpaint` / `is_active_prompt_reverse`: 是否启用。
- `status`: 配置状态，常见为 `enabled`。
- `created_at` / `updated_at`: 创建时间、更新时间。

### `external_api_scene_bindings`

- `scene_key`: 场景唯一键，例如不同生图、编辑或反推场景。
- `is_deleted`: 是否逻辑删除；后台通常只展示未删除记录。
- `scene_type`: 场景类型。
- `scene_label` / `scene_description`: 场景文案。
- `sort_order`: 场景排序。
- `api_config_id`: 绑定的接口配置。
- `display_name` / `subtitle`: 前端展示名称与副标题。
- `credit_cost`: 该场景的默认单任务积分成本。
- `max_reference_images`: 该场景允许上传的最大参考图数量；图编辑模型常依赖这个值控制前端上传上限。
- `hide_aspect_ratio` / `hide_resolution` / `hide_custom_size`: 前端是否隐藏相关参数；`hide_custom_size=0` 表示支持用户手动输入自定义分辨率。
- `custom_size_min` / `custom_size_max` / `custom_size_step`: 自定义分辨率宽高的最小值、最大值与递增步长。
- `aspect_ratio_options_json` / `image_size_options_json` / `custom_size_options_json`: 可选参数列表。
- `resolution_mapping_json`: 分辨率映射对象，用于把宽高比和生图质量映射为第三方接口的单个分辨率参数。
- `resolution_credit_costs_json`: 分辨率积分对象，用于按生图质量覆盖默认积分成本，例如 `{"1K":2,"2K":4,"4K":8}`。
- `status`: 场景状态，常见为 `enabled`。
- `updated_at`: 最后更新时间。

### `generation_scene_categories`

- `name` / `description`: 分类名称与说明。
- `scene_type`: 分类所属能力，`generate`（文生图）或 `image_edit`（图编辑）。分类只能选择同类型场景。
- `scene_keys_json`: 该分类包含的场景标识数组，例如 `["banana_pro","banana2"]`。一个场景最多属于一个未删除分类。
- `sort_order`: 分类在生图模型下拉中的排序。
- `status`: 分类状态，`enabled` / `disabled`。停用后场景按未分类展示。
- `is_deleted`: 是否逻辑删除。
- `created_at` / `updated_at`: 创建时间、更新时间。

### `history_pins`

- `user_id`: 置顶归属用户。
- `item_type`: 置顶项类型，当前默认 `task`。
- `item_key`: 置顶项唯一键；前端通常使用业务 ID 或兼容标识符。
- `image_id` / `history_id`: 兼容旧历史结构的补充引用字段。
- `pinned_at`: 实际置顶时间。
- `created_at`: 记录创建时间。
- 使用联合唯一约束 `(user_id, item_key)` 保证同一用户不会重复置顶同一项。
- 使用组合索引 `(user_id, pinned_at)` 优化按用户查询置顶列表与按置顶时间倒序展示。

### `feedback`

- `business_id`: Feedback 对外业务 ID，32 位十六进制字符串。
- `user_id`: 提交反馈的用户。
- `task_id`: 关联任务。
- `content`: 用户反馈内容。
- `status`: 处理状态，当前默认 `pending`。
- `is_read`: 用户侧是否已读；`0` 表示未读，`1` 表示已读，默认 `0`。
- `process_note`: 处理过程备注。
- `result_note`: 处理结果备注。
- `handled_by`: 处理人。
- `handled_at`: 处理时间。
- `created_at` / `updated_at`: 创建时间、更新时间。

### `system_messages`

- `business_id`: 系统消息对外业务 ID，32 位十六进制字符串。
- `subject`: 消息主题。
- `content_html`: 富文本正文，应用层会进行基础 HTML 清理；图片可保存为 base64 data URL。
- `content_text`: 从富文本正文提取的纯文本摘要。
- `sender_id`: 发送管理员。
- `recipient_scope`: 接收范围，`selected` 表示指定用户，`all` 表示发送时快照全部可用用户。
- `recipient_count`: 发送时实际生成的收件人数。
- `created_at` / `updated_at`: 创建时间、更新时间。

### `system_message_recipients`

- `message_id`: 关联系统消息。
- `user_id`: 接收用户。
- `is_read`: 用户侧是否已读；`0` 表示未读，`1` 表示已读，默认 `0`。
- `read_at`: 用户首次打开详情并标记已读的时间。
- `created_at`: 收件记录创建时间。
- 使用联合唯一约束 `(message_id, user_id)` 保证同一消息不会重复投递给同一用户。

### `regenerate_logs`

- `image_id`: 被重绘的原图片 ID。
- `old_image_url`: 重绘前图片地址。
- `new_image_url`: 重绘后图片地址。
- `created_at`: 重绘记录时间。

## 任务耗时计算口径

以下口径与当前后端日志和字段语义保持一致。

### 推荐口径

- 排队耗时：`enqueued_at - created_at`
- 总耗时：`updated_at - created_at`
- 实际处理耗时：`updated_at - enqueued_at`

### 说明

- `created_at` 记录任务写入数据库的时间。
- `enqueued_at` 记录任务成功进入分发/入队流程的时间。
- `updated_at` 记录任务最近一次状态变化的时间；任务最终完成或失败后可视为结束时间。
- 若 `enqueued_at` 为空，通常表示任务尚未成功分发，或该记录产生于旧版本逻辑。
- `实际处理耗时` 目前是基于数据库时间字段估算；若要做到最精确分析，建议后续再增加 `started_at` / `finished_at` 字段。

### 常用 SQL 示例

```sql
-- 查看最近任务的排队耗时、处理耗时、总耗时（毫秒）
SELECT
  id,
  user_id,
  status,
  created_at,
  enqueued_at,
  updated_at,
  CASE
    WHEN enqueued_at IS NOT NULL THEN TIMESTAMPDIFF(MICROSECOND, created_at, enqueued_at) / 1000
    ELSE NULL
  END AS queue_duration_ms,
  CASE
    WHEN enqueued_at IS NOT NULL THEN TIMESTAMPDIFF(MICROSECOND, enqueued_at, updated_at) / 1000
    ELSE NULL
  END AS processing_duration_ms,
  TIMESTAMPDIFF(MICROSECOND, created_at, updated_at) / 1000 AS total_duration_ms
FROM tasks
ORDER BY id DESC
LIMIT 50;

-- 查看失败任务及其耗时
SELECT
  id,
  user_id,
  model,
  mode,
  status,
  error_message,
  TIMESTAMPDIFF(MICROSECOND, created_at, updated_at) / 1000 AS total_duration_ms
FROM tasks
WHERE status = 'failed'
ORDER BY id DESC
LIMIT 50;

-- 按用户统计平均排队耗时与总耗时
SELECT
  user_id,
  COUNT(*) AS task_count,
  AVG(
    CASE
      WHEN enqueued_at IS NOT NULL THEN TIMESTAMPDIFF(MICROSECOND, created_at, enqueued_at) / 1000
      ELSE NULL
    END
  ) AS avg_queue_duration_ms,
  AVG(TIMESTAMPDIFF(MICROSECOND, created_at, updated_at) / 1000) AS avg_total_duration_ms
FROM tasks
GROUP BY user_id
ORDER BY task_count DESC;
```

## 默认账号

| 用户名 | 初始密码 | 角色 |
|--------|----------|------|
| `administrator` | `administrator123` | `superadmin`（超级管理员） |
| `admin` | `admin123` | `admin`（管理员） |

## SQL

```sql
SET NAMES utf8mb4;

CREATE TABLE api_keys (
  id INT NOT NULL AUTO_INCREMENT,
  `key` VARCHAR(255) NOT NULL,
  tongyi_key VARCHAR(255) NOT NULL,
  contact_qr_image VARCHAR(500) NOT NULL,
  cos_secret_id VARCHAR(255) NOT NULL,
  cos_secret_key VARCHAR(255) NOT NULL,
  cos_bucket VARCHAR(255) NOT NULL,
  cos_region VARCHAR(100) NOT NULL,
  cos_upload_domain VARCHAR(500) NOT NULL,
  cos_public_base_url VARCHAR(500) NOT NULL,
  announcement_enabled INT NOT NULL,
  announcement_content VARCHAR(5000) NOT NULL,
  announcement_updated_at DATETIME NULL,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE external_api_configs (
  id INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL,
  description VARCHAR(255) NOT NULL DEFAULT '',
  group_name VARCHAR(100) NOT NULL DEFAULT '默认',
  model_key VARCHAR(50) NOT NULL DEFAULT '',
  model_label VARCHAR(100) NOT NULL DEFAULT '',
  model_description VARCHAR(255) NOT NULL DEFAULT '',
  sort_order INT NOT NULL DEFAULT 0,
  hide_resolution TINYINT(1) NOT NULL DEFAULT 0,
  request_url VARCHAR(500) NOT NULL DEFAULT '',
  request_format VARCHAR(20) NOT NULL DEFAULT 'json',
  headers_json TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  response_json TEXT NOT NULL,
  result_base64_field VARCHAR(255) NOT NULL DEFAULT '',
  supports_generation TINYINT(1) NOT NULL DEFAULT 0,
  supports_inpaint TINYINT(1) NOT NULL DEFAULT 0,
  supports_prompt_reverse TINYINT(1) NOT NULL DEFAULT 0,
  is_active_generation TINYINT(1) NOT NULL DEFAULT 0,
  is_active_inpaint TINYINT(1) NOT NULL DEFAULT 0,
  is_active_prompt_reverse TINYINT(1) NOT NULL DEFAULT 0,
  status VARCHAR(20) NOT NULL DEFAULT 'enabled',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_external_api_configs_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE template_tags (
  id INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(50) NOT NULL,
  UNIQUE KEY uq_template_tags_name (name),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE templates (
  id INT NOT NULL AUTO_INCREMENT,
  prompt TEXT NOT NULL,
  model VARCHAR(50) DEFAULT 'banana_pro',
  reference_images TEXT,
  size VARCHAR(20) DEFAULT '1:1',
  resolution VARCHAR(10) DEFAULT '2K',
  custom_size VARCHAR(50) DEFAULT '',
  num_images INT DEFAULT 1,
  result_image VARCHAR(255) DEFAULT '',
  sort_order INT DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE users (
  id INT NOT NULL AUTO_INCREMENT,
  business_id VARCHAR(32) NOT NULL,
  username VARCHAR(50) NOT NULL,
  email VARCHAR(255) DEFAULT NULL,
  email_verified TINYINT(1) NOT NULL DEFAULT 0,
  password_hash VARCHAR(255) NOT NULL,
  avatar_url VARCHAR(500) DEFAULT '',
  `role` VARCHAR(20) DEFAULT 'user',
  status VARCHAR(10) DEFAULT 'active',
  is_whitelisted TINYINT(1) NOT NULL DEFAULT 0,
  invite_code VARCHAR(16) DEFAULT NULL,
  referrer_id INT DEFAULT NULL,
  used_promo_code_id INT DEFAULT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_business_id (business_id),
  UNIQUE KEY ux_users_invite_code (invite_code),
  KEY ix_users_referrer_id (referrer_id),
  KEY ix_users_used_promo_code_id (used_promo_code_id),
  CONSTRAINT fk_users_referrer_id FOREIGN KEY (referrer_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE user_promo_codes (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  code VARCHAR(32) NOT NULL,
  platform_name VARCHAR(50) NOT NULL DEFAULT '',
  status VARCHAR(20) NOT NULL DEFAULT 'enabled',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_user_promo_codes_code (code),
  KEY ix_user_promo_codes_user_id (user_id),
  KEY ix_user_promo_codes_code (code),
  KEY ix_user_promo_codes_status (status),
  CONSTRAINT fk_user_promo_codes_user_id FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE referral_reward_grants (
  id INT NOT NULL AUTO_INCREMENT,
  referrer_id INT NOT NULL,
  invitee_id INT NOT NULL,
  source_type VARCHAR(20) NOT NULL,
  source_id VARCHAR(64) NOT NULL,
  source_credits INT NOT NULL DEFAULT 0,
  reward_rate INT NOT NULL DEFAULT 15,
  reward_credits INT NOT NULL DEFAULT 0,
  reward_index INT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_referral_reward_grants_referrer_id (referrer_id),
  KEY ix_referral_reward_grants_invitee_id (invitee_id),
  KEY ix_referral_reward_grants_source_type (source_type),
  KEY ix_referral_reward_grants_source_id (source_id),
  UNIQUE KEY ux_referral_reward_source (source_type, source_id, referrer_id),
  UNIQUE KEY ux_referral_reward_index (referrer_id, invitee_id, reward_index),
  CONSTRAINT fk_referral_reward_referrer_id FOREIGN KEY (referrer_id) REFERENCES users (id),
  CONSTRAINT fk_referral_reward_invitee_id FOREIGN KEY (invitee_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE promo_reward_grants (
  id INT NOT NULL AUTO_INCREMENT,
  referrer_id INT NOT NULL,
  invitee_id INT NOT NULL,
  promo_code_id INT NULL,
  source_type VARCHAR(20) NOT NULL,
  source_id VARCHAR(64) NOT NULL,
  source_credits INT NOT NULL DEFAULT 0,
  source_amount_fen INT NOT NULL DEFAULT 0,
  reward_rate INT NOT NULL DEFAULT 30,
  reward_amount_fen INT NOT NULL DEFAULT 0,
  reward_index INT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
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

CREATE TABLE user_credits (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  type INT NOT NULL DEFAULT 0,
  remain_credit INT NOT NULL DEFAULT 0,
  used_credit INT NOT NULL DEFAULT 0,
  status TINYINT(1) NOT NULL DEFAULT 1,
  expire_time DATETIME NOT NULL DEFAULT '2027-12-30 23:59:59',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_user_credits_user_id_type (user_id, type),
  KEY ix_user_credits_user_id (user_id),
  KEY ix_user_credits_type (type),
  CONSTRAINT fk_user_credits_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE user_canvas (
  id INT NOT NULL AUTO_INCREMENT,
  project_id VARCHAR(16) NOT NULL,
  user_id INT NOT NULL,
  name VARCHAR(100) NOT NULL DEFAULT '',
  viewport_x DOUBLE NOT NULL DEFAULT 0,
  viewport_y DOUBLE NOT NULL DEFAULT 0,
  zoom DOUBLE NOT NULL DEFAULT 1,
  is_deleted TINYINT(1) NOT NULL DEFAULT 0,
  deleted_at DATETIME DEFAULT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY idx_user_canvas_project_id (project_id),
  KEY idx_user_canvas_user_id (user_id),
  KEY idx_user_canvas_user_updated_at (user_id, updated_at),
  KEY idx_user_canvas_user_deleted_updated (user_id, is_deleted, updated_at),
  CONSTRAINT fk_user_canvas_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE user_boards (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  name VARCHAR(100) NOT NULL DEFAULT '',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_user_boards_user_id (user_id),
  CONSTRAINT fk_user_boards_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE canvas_groups (
  id INT NOT NULL AUTO_INCREMENT,
  canvas_id INT NOT NULL,
  name VARCHAR(100) NOT NULL DEFAULT '',
  color VARCHAR(32) NOT NULL DEFAULT '#ffab27',
  x DOUBLE NOT NULL DEFAULT 0,
  y DOUBLE NOT NULL DEFAULT 0,
  width DOUBLE NOT NULL DEFAULT 320,
  height DOUBLE NOT NULL DEFAULT 220,
  z_index INT NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_canvas_groups_canvas_id (canvas_id),
  KEY idx_canvas_groups_canvas_z (canvas_id, z_index),
  CONSTRAINT fk_canvas_groups_canvas FOREIGN KEY (canvas_id) REFERENCES user_canvas (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE external_api_scene_bindings (
  id INT NOT NULL AUTO_INCREMENT,
  scene_key VARCHAR(50) NOT NULL,
  is_deleted TINYINT(1) NOT NULL DEFAULT 0,
  scene_type VARCHAR(30) NOT NULL DEFAULT 'generate',
  scene_label VARCHAR(100) NOT NULL DEFAULT '',
  scene_description VARCHAR(255) NOT NULL DEFAULT '',
  sort_order INT NOT NULL DEFAULT 0,
  hide_aspect_ratio TINYINT(1) NOT NULL DEFAULT 0,
  hide_resolution TINYINT(1) NOT NULL DEFAULT 0,
  hide_custom_size TINYINT(1) NOT NULL DEFAULT 1,
  custom_size_min INT NOT NULL DEFAULT 256,
  custom_size_max INT NOT NULL DEFAULT 4096,
  custom_size_step INT NOT NULL DEFAULT 8,
  status VARCHAR(20) NOT NULL DEFAULT 'enabled',
  api_config_id INT DEFAULT NULL,
  display_name VARCHAR(100) NOT NULL DEFAULT '',
  subtitle VARCHAR(255) NOT NULL DEFAULT '',
  credit_cost INT NOT NULL DEFAULT 0,
  max_reference_images INT NOT NULL DEFAULT 0,
  aspect_ratio_options_json TEXT NOT NULL,
  image_size_options_json TEXT NOT NULL,
  custom_size_options_json TEXT NOT NULL,
  resolution_mapping_json TEXT NOT NULL,
  resolution_credit_costs_json TEXT NOT NULL,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_external_api_scene_bindings_scene_key (scene_key),
  CONSTRAINT fk_scene_api_config FOREIGN KEY (api_config_id) REFERENCES external_api_configs (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE generation_scene_categories (
  id INT NOT NULL AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL,
  description VARCHAR(255) NOT NULL DEFAULT '',
  scene_type VARCHAR(20) NOT NULL DEFAULT 'generate',
  scene_keys_json TEXT NOT NULL,
  sort_order INT NOT NULL DEFAULT 100,
  status VARCHAR(20) NOT NULL DEFAULT 'enabled',
  is_deleted TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_generation_scene_categories_sort (sort_order, id),
  KEY idx_generation_scene_categories_status (status, is_deleted),
  KEY idx_generation_scene_categories_scene_type (scene_type, is_deleted)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE prompt_history (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  prompt VARCHAR(2000) NOT NULL,
  mode VARCHAR(20) NOT NULL DEFAULT 'generate',
  source_image VARCHAR(500) NOT NULL DEFAULT '',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_prompt_history_user_id (user_id),
  CONSTRAINT fk_prompt_history_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE tasks (
  id INT NOT NULL AUTO_INCREMENT,
  business_id VARCHAR(32) NOT NULL,
  user_id INT NOT NULL,
  board_id INT DEFAULT NULL,
  model VARCHAR(50) DEFAULT '',
  source VARCHAR(20) NOT NULL DEFAULT 'web',
  mode VARCHAR(20) DEFAULT 'generate',
  prompt TEXT,
  num_images INT DEFAULT 4,
  size VARCHAR(20) DEFAULT '3:4',
  resolution VARCHAR(10) DEFAULT '4K',
  custom_size VARCHAR(50) DEFAULT '',
  reference_image VARCHAR(500) DEFAULT '',
  reference_images TEXT,
  source_image VARCHAR(500) DEFAULT '',
  mask_image VARCHAR(500) DEFAULT '',
  canvas_id INT DEFAULT NULL,
  credit_cost INT NOT NULL DEFAULT 0,
  status VARCHAR(20) DEFAULT 'pending',
  error_message TEXT,
  is_deleted TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  enqueued_at DATETIME DEFAULT NULL,
  request_started_at DATETIME DEFAULT NULL,
  request_finished_at DATETIME DEFAULT NULL,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_tasks_business_id (business_id),
  KEY idx_tasks_board_id (board_id),
  KEY idx_tasks_canvas_id (canvas_id),
  KEY idx_tasks_user_canvas_deleted_created (user_id, canvas_id, is_deleted, created_at),
  CONSTRAINT fk_tasks_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_tasks_board FOREIGN KEY (board_id) REFERENCES user_boards (id) ON DELETE SET NULL,
  CONSTRAINT fk_tasks_canvas FOREIGN KEY (canvas_id) REFERENCES user_canvas (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE canvas_nodes (
  id INT NOT NULL AUTO_INCREMENT,
  canvas_id INT NOT NULL,
  group_id INT DEFAULT NULL,
  task_id INT DEFAULT NULL,
  node_type VARCHAR(20) NOT NULL DEFAULT 'task',
  content VARCHAR(5000) NOT NULL DEFAULT '',
  image_url VARCHAR(1000) NOT NULL DEFAULT '',
  x DOUBLE NOT NULL DEFAULT 0,
  y DOUBLE NOT NULL DEFAULT 0,
  width DOUBLE NOT NULL DEFAULT 320,
  height DOUBLE NOT NULL DEFAULT 420,
  z_index INT NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_canvas_nodes_canvas_id (canvas_id),
  KEY idx_canvas_nodes_group_id (group_id),
  KEY idx_canvas_nodes_canvas_z (canvas_id, z_index),
  KEY idx_canvas_nodes_task_id (task_id),
  CONSTRAINT fk_canvas_nodes_canvas FOREIGN KEY (canvas_id) REFERENCES user_canvas (id),
  CONSTRAINT fk_canvas_nodes_group FOREIGN KEY (group_id) REFERENCES canvas_groups (id) ON DELETE SET NULL,
  CONSTRAINT fk_canvas_nodes_task FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE canvas_edges (
  id INT NOT NULL AUTO_INCREMENT,
  canvas_id INT NOT NULL,
  source_node_id INT NOT NULL,
  target_node_id INT NOT NULL,
  edge_type VARCHAR(20) NOT NULL DEFAULT 'reference',
  source_anchor VARCHAR(10) NOT NULL DEFAULT 'auto',
  target_anchor VARCHAR(10) NOT NULL DEFAULT 'auto',
  is_collapsed TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_canvas_edges_canvas_id (canvas_id),
  KEY idx_canvas_edges_source_node_id (source_node_id),
  KEY idx_canvas_edges_target_node_id (target_node_id),
  CONSTRAINT fk_canvas_edges_canvas FOREIGN KEY (canvas_id) REFERENCES user_canvas (id) ON DELETE CASCADE,
  CONSTRAINT fk_canvas_edges_source_node FOREIGN KEY (source_node_id) REFERENCES canvas_nodes (id) ON DELETE CASCADE,
  CONSTRAINT fk_canvas_edges_target_node FOREIGN KEY (target_node_id) REFERENCES canvas_nodes (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE template_tag_relations (
  template_id INT NOT NULL,
  tag_id INT NOT NULL,
  PRIMARY KEY (template_id, tag_id),
  CONSTRAINT fk_ttr_template FOREIGN KEY (template_id) REFERENCES templates (id),
  CONSTRAINT fk_ttr_tag FOREIGN KEY (tag_id) REFERENCES template_tags (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE credit_logs (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  amount INT NOT NULL,
  type VARCHAR(20) NOT NULL,
  description VARCHAR(500) DEFAULT '',
  operator_id INT DEFAULT NULL,
  task_id INT DEFAULT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_credit_logs_user_id (user_id),
  CONSTRAINT fk_credit_logs_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_credit_logs_operator FOREIGN KEY (operator_id) REFERENCES users (id),
  CONSTRAINT fk_credit_logs_task FOREIGN KEY (task_id) REFERENCES tasks (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE credit_redeem_keys (
  id INT NOT NULL AUTO_INCREMENT,
  redeem_key VARCHAR(16) NOT NULL,
  credit_amount INT NOT NULL DEFAULT 0,
  batch_no VARCHAR(32) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'enabled',
  created_by INT DEFAULT NULL,
  used_by_user_id INT DEFAULT NULL,
  used_at DATETIME DEFAULT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_credit_redeem_keys_redeem_key (redeem_key),
  KEY ix_credit_redeem_keys_redeem_key (redeem_key),
  KEY ix_credit_redeem_keys_batch_no (batch_no),
  KEY ix_credit_redeem_keys_status (status),
  KEY ix_credit_redeem_keys_created_by (created_by),
  KEY ix_credit_redeem_keys_used_by_user_id (used_by_user_id),
  CONSTRAINT fk_credit_redeem_keys_created_by FOREIGN KEY (created_by) REFERENCES users (id),
  CONSTRAINT fk_credit_redeem_keys_used_by_user_id FOREIGN KEY (used_by_user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE payment_orders (
  id INT NOT NULL AUTO_INCREMENT,
  order_no VARCHAR(64) NOT NULL,
  user_id INT NOT NULL,
  plan_key VARCHAR(50) NOT NULL DEFAULT '',
  subject VARCHAR(255) NOT NULL DEFAULT '',
  amount_fen INT NOT NULL DEFAULT 0,
  credits INT NOT NULL DEFAULT 0,
  status VARCHAR(20) NOT NULL DEFAULT 'created',
  out_trade_no VARCHAR(64) NOT NULL,
  alipay_trade_no VARCHAR(64) DEFAULT NULL,
  buyer_id VARCHAR(64) NOT NULL DEFAULT '',
  trade_status VARCHAR(32) NOT NULL DEFAULT '',
  notify_payload LONGTEXT DEFAULT NULL,
  return_payload LONGTEXT DEFAULT NULL,
  paid_at DATETIME DEFAULT NULL,
  credited_at DATETIME DEFAULT NULL,
  closed_at DATETIME DEFAULT NULL,
  failed_at DATETIME DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_payment_orders_order_no (order_no),
  UNIQUE KEY uq_payment_orders_out_trade_no (out_trade_no),
  UNIQUE KEY uq_payment_orders_alipay_trade_no (alipay_trade_no),
  KEY ix_payment_orders_user_id (user_id),
  KEY ix_payment_orders_status (status),
  KEY ix_payment_orders_user_created_at (user_id, created_at),
  CONSTRAINT fk_payment_orders_user_id FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE offline_orders (
  id INT NOT NULL AUTO_INCREMENT,
  business_id VARCHAR(32) NOT NULL,
  user_id INT NOT NULL,
  order_type VARCHAR(20) NOT NULL DEFAULT 'purchase',
  credit_amount INT NOT NULL DEFAULT 0,
  amount_fen INT NOT NULL DEFAULT 0,
  remark VARCHAR(500) NOT NULL DEFAULT '',
  created_by INT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_offline_orders_business_id (business_id),
  KEY ix_offline_orders_business_id (business_id),
  KEY ix_offline_orders_user_id (user_id),
  KEY ix_offline_orders_order_type (order_type),
  KEY ix_offline_orders_created_by (created_by),
  CONSTRAINT fk_offline_orders_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_offline_orders_created_by FOREIGN KEY (created_by) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE user_api_key (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  subs_type VARCHAR(50) NOT NULL DEFAULT '',
  expire_time DATETIME DEFAULT NULL,
  api_key VARCHAR(35) NOT NULL,
  key_name VARCHAR(100) NOT NULL DEFAULT '',
  status VARCHAR(20) NOT NULL DEFAULT 'enabled',
  is_delete TINYINT(1) NOT NULL DEFAULT 0,
  key_prefix VARCHAR(8) NOT NULL DEFAULT '',
  key_last4 VARCHAR(4) NOT NULL DEFAULT '',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_user_api_key_api_key (api_key),
  KEY ix_user_api_key_user_id (user_id),
  KEY ix_user_api_key_status (status),
  KEY ix_user_api_key_is_delete (is_delete),
  CONSTRAINT fk_user_api_key_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE images (
  id INT NOT NULL AUTO_INCREMENT,
  task_id INT DEFAULT NULL,
  image_url VARCHAR(255) DEFAULT '',
  preview_url VARCHAR(500) DEFAULT '',
  image_format VARCHAR(20) DEFAULT '',
  image_size_bytes INT DEFAULT 0,
  status VARCHAR(20) DEFAULT 'pending',
  error_message VARCHAR(2000) DEFAULT '',
  is_deleted TINYINT(1) NOT NULL DEFAULT 0,
  deleted_at DATETIME DEFAULT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_images_task FOREIGN KEY (task_id) REFERENCES tasks (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE history_pins (
  id INT NOT NULL AUTO_INCREMENT,
  user_id INT NOT NULL,
  item_type VARCHAR(20) NOT NULL DEFAULT 'task',
  item_key VARCHAR(64) NOT NULL,
  image_id INT DEFAULT NULL,
  history_id INT DEFAULT NULL,
  pinned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_history_pins_user_id (user_id),
  KEY ix_history_pins_user_pinned_at (user_id, pinned_at DESC),
  UNIQUE KEY ux_history_pins_user_item_key (user_id, item_key),
  CONSTRAINT fk_history_pins_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE feedback (
  id INT NOT NULL AUTO_INCREMENT,
  business_id VARCHAR(32) NOT NULL,
  user_id INT NOT NULL,
  task_id INT DEFAULT NULL,
  content TEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  is_read TINYINT(1) NOT NULL DEFAULT 0,
  process_note VARCHAR(5000) NOT NULL DEFAULT '',
  result_note VARCHAR(5000) NOT NULL DEFAULT '',
  handled_by INT DEFAULT NULL,
  handled_at DATETIME DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_feedback_business_id (business_id),
  KEY ix_feedback_user_id (user_id),
  KEY ix_feedback_task_id (task_id),
  KEY ix_feedback_status (status),
  KEY ix_feedback_is_read (is_read),
  KEY ix_feedback_handled_by (handled_by),
  CONSTRAINT fk_feedback_user FOREIGN KEY (user_id) REFERENCES users (id),
  CONSTRAINT fk_feedback_task FOREIGN KEY (task_id) REFERENCES tasks (id),
  CONSTRAINT fk_feedback_handled_by FOREIGN KEY (handled_by) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE system_messages (
  id INT NOT NULL AUTO_INCREMENT,
  business_id VARCHAR(32) NOT NULL,
  subject VARCHAR(200) NOT NULL,
  content_html LONGTEXT NOT NULL,
  content_text LONGTEXT NOT NULL,
  sender_id INT NOT NULL,
  recipient_scope VARCHAR(20) NOT NULL DEFAULT 'selected',
  recipient_count INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_system_messages_business_id (business_id),
  KEY ix_system_messages_subject (subject),
  KEY ix_system_messages_sender_id (sender_id),
  KEY ix_system_messages_recipient_scope (recipient_scope),
  CONSTRAINT fk_system_messages_sender FOREIGN KEY (sender_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE system_message_recipients (
  id INT NOT NULL AUTO_INCREMENT,
  message_id INT NOT NULL,
  user_id INT NOT NULL,
  is_read TINYINT(1) NOT NULL DEFAULT 0,
  read_at DATETIME DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_system_message_recipient_message_user (message_id, user_id),
  KEY ix_system_message_recipients_message_id (message_id),
  KEY ix_system_message_recipients_user_id (user_id),
  KEY ix_system_message_recipients_is_read (is_read),
  CONSTRAINT fk_system_message_recipients_message FOREIGN KEY (message_id) REFERENCES system_messages (id),
  CONSTRAINT fk_system_message_recipients_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE regenerate_logs (
  id INT NOT NULL AUTO_INCREMENT,
  image_id INT NOT NULL,
  old_image_url VARCHAR(255) DEFAULT '',
  new_image_url VARCHAR(255) DEFAULT '',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  CONSTRAINT fk_regenerate_logs_image FOREIGN KEY (image_id) REFERENCES images (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE UNIQUE INDEX ix_users_email ON users (email);
CREATE INDEX ix_users_username ON users (username);

INSERT INTO users (
  business_id, username, email, email_verified, password_hash, avatar_url,
  `role`, status, is_whitelisted, created_at, updated_at
) VALUES
('11111111111111111111111111111111', 'administrator', NULL, 0, '$2b$12$CR1qnIGjLbi46hgFXXrxQOoPge5g0aWWuLga1fWGDC5GOBiIFY0vK', '', 'superadmin', 'active', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
('22222222222222222222222222222222', 'admin', NULL, 0, '$2b$12$gGceM8aYPCpT9Kz0GJQvje0cvIS5y6HEFrXTGyeu4AzNbD7ANX..C', '', 'admin', 'active', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

INSERT INTO user_credits (user_id, type, remain_credit, used_credit, status, expire_time, created_at, updated_at)
SELECT id, 0, 0, 0, 1, '2027-12-30 23:59:59', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
FROM users
WHERE business_id IN (
  '11111111111111111111111111111111',
  '22222222222222222222222222222222'
);
```