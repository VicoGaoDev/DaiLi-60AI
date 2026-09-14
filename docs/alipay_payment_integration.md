# 支付宝支付配置与实现说明

## 1. 目标

本文档说明 80AI 中积分套餐支付宝直连支付的配置方式、后端实现结构、前端支付流程，以及本地联调和正式环境部署注意事项。

## 2. 当前实现概览

当前项目已实现 PC Web 积分套餐支付宝直连支付，主要流程如下：

1. 前端调用后端创建支付订单
2. 后端生成本地 `payment_orders` 订单记录
3. 后端使用支付宝 `alipay.trade.page.pay` 生成电脑网站支付收银台地址
4. 前端跳转到支付宝收银台，用户可在支付宝页面扫码或登录支付
5. 支付宝异步通知后端 `notify_url`
6. 后端验签成功后更新订单状态并发放积分
7. 前端弹窗与结果页轮询订单状态，显示支付结果并刷新积分

## 3. 相关代码位置

### 后端

- `backend/app/models/payment_order.py`
- `backend/app/schemas/payment.py`
- `backend/app/services/payment_service.py`
- `backend/app/api/payment.py`
- `backend/app/config.py`
- `backend/app/main.py`

### 前端

- `frontend/src/api/payments.ts`
- `frontend/src/components/layout/AppLayout.vue`
- `frontend/src/views/PaymentResultView.vue`
- `frontend/src/router/index.ts`

### 文档与配置

- `backend/.env.example`
- `docs/mysql_empty_database_init.md`
- `README.md`

## 4. 后端环境变量说明

以下变量均为后端环境变量：

```env
ALIPAY_APP_ID=
ALIPAY_PRIVATE_KEY=
ALIPAY_PUBLIC_KEY=
ALIPAY_GATEWAY=https://openapi.alipay.com/gateway.do
ALIPAY_NOTIFY_URL=https://api.example.com/api/payment/webhook/alipay
ALIPAY_RETURN_URL=https://web.example.com/payment-result
ALIPAY_SIGN_TYPE=RSA2
ALIPAY_TIMEOUT_EXPRESS=15m
```

### 字段含义

- `ALIPAY_APP_ID`
  支付宝开放平台应用的 AppID。

- `ALIPAY_PRIVATE_KEY`
  应用私钥，由商户自己生成，用于后端请求签名。

- `ALIPAY_PUBLIC_KEY`
  支付宝公钥，由支付宝平台提供，用于后端验签异步通知。

- `ALIPAY_GATEWAY`
  支付宝网关地址。
  - 正式环境：`https://openapi.alipay.com/gateway.do`
  - 沙箱环境：以支付宝沙箱控制台提供地址为准

- `ALIPAY_NOTIFY_URL`
  支付宝异步通知地址，必须为后端公网 HTTPS 地址。

- `ALIPAY_RETURN_URL`
  支付完成后前端结果页地址，用于展示支付结果或兜底轮询。

- `ALIPAY_SIGN_TYPE`
  当前使用 `RSA2`。

- `ALIPAY_TIMEOUT_EXPRESS`
  订单超时时间，例如 `15m`。

## 5. 密钥说明

支付宝相关密钥分为三种概念。

### 5.1 应用私钥

- 由自己生成
- 保存在后端环境变量中
- 对应配置项：`ALIPAY_PRIVATE_KEY`

### 5.2 应用公钥

- 由应用私钥推导得到
- 上传到支付宝开放平台
- 用于支付宝验证商户请求签名
- 当前项目后端不直接配置该值

### 5.3 支付宝公钥

- 由支付宝提供
- 保存在后端环境变量中
- 对应配置项：`ALIPAY_PUBLIC_KEY`
- 用于后端验证支付宝异步通知签名

## 6. 支付流程说明

### 6.1 创建订单

前端选择积分套餐后，请求：

- `POST /api/payment/orders`

请求参数：

```json
{
  "plan_key": "starter"
}
```

后端处理逻辑：

1. 校验支付宝配置是否完整
2. 根据 `plan_key` 读取后端商品表
3. 创建本地订单记录
4. 调用支付宝 `alipay.trade.page.pay` 生成收银台跳转地址
5. 返回前端支付跳转地址

### 6.2 支付宝收银台

前端收到后端返回的 `pay_url` 后，直接跳转到支付宝电脑网站支付收银台。用户可在支付宝收银台页面使用手机支付宝扫码支付，也可以按支付宝页面提示登录后完成支付。

### 6.3 异步回调

支付宝支付完成后，会调用：

- `POST /api/payment/webhook/alipay`

后端处理逻辑：

1. 接收支付宝异步通知参数
2. 使用 `ALIPAY_PUBLIC_KEY` 验签
3. 校验 `app_id`、订单号、金额
4. 查找本地支付订单并加锁
5. 若订单未入账，则更新为 `paid`
6. 调用积分服务发放积分
7. 订单状态更新为 `credited`
8. 返回纯文本 `success`

### 6.4 前端结果页

前端结果页：

- `/payment-result`

页面会轮询：

- `GET /api/payment/orders/{order_no}`

当本地订单仍处于 `pending_pay` / `paid` 状态时，后端会主动调用支付宝 `alipay.trade.query` 查单作为兜底，避免因异步通知延迟导致前端长时间停留在处理中状态。

订单状态说明：

- `pending_pay`：待支付
- `paid`：已支付，积分处理中
- `credited`：积分已到账
- `closed`：订单已关闭
- `failed`：支付失败

## 7. 数据表说明

支付订单表：

- `payment_orders`

关键字段包括：

- `order_no`
- `user_id`
- `plan_key`
- `subject`
- `amount_fen`
- `credits`
- `status`
- `out_trade_no`
- `alipay_trade_no`
- `buyer_id`
- `trade_status`
- `notify_payload`
- `return_payload`
- `paid_at`
- `credited_at`

详细 SQL 可参考：

- `docs/mysql_empty_database_init.md`

## 8. 本地联调说明

### 8.1 本地环境

本地开发配置写入：

- `backend/.env`

示例：

```env
ALIPAY_APP_ID=沙箱APPID
ALIPAY_PRIVATE_KEY=沙箱应用私钥
ALIPAY_PUBLIC_KEY=沙箱支付宝公钥
ALIPAY_GATEWAY=https://openapi-sandbox.dl.alipaydev.com/gateway.do
ALIPAY_NOTIFY_URL=https://your-public-domain/api/payment/webhook/alipay
ALIPAY_RETURN_URL=http://localhost:3000/payment-result
ALIPAY_SIGN_TYPE=RSA2
ALIPAY_TIMEOUT_EXPRESS=15m
```

### 8.2 注意事项

- `ALIPAY_NOTIFY_URL` 不能使用 `localhost`
- 需要内网穿透工具提供公网地址
- 支付结果以后端异步通知为准
- 弹窗轮询与结果页都只负责展示状态，不直接决定积分到账

## 9. 正式环境部署说明

正式环境不要把真实密钥写进仓库。

推荐方式：

- `backend/.env.example` 只保留占位模板
- 本地开发使用 `backend/.env`
- 正式环境通过部署平台环境变量注入

正式环境需要配置：

- `ALIPAY_APP_ID`
- `ALIPAY_PRIVATE_KEY`
- `ALIPAY_PUBLIC_KEY`
- `ALIPAY_GATEWAY`
- `ALIPAY_NOTIFY_URL`
- `ALIPAY_RETURN_URL`
- `ALIPAY_SIGN_TYPE`
- `ALIPAY_TIMEOUT_EXPRESS`

## 10. 常见问题

### 10.1 支付宝支付配置不完整

说明后端缺少必要环境变量。

后端会返回缺失项名称，例如：

```json
{
  "detail": "支付宝支付配置不完整，缺少: ALIPAY_APP_ID, ALIPAY_NOTIFY_URL"
}
```

### 10.2 异步通知收不到

常见原因：

- `notify_url` 不是公网地址
- 内网穿透未启动
- 回调路径错误
- 防火墙或网关拦截
- 验签失败

### 10.3 扫码后积分没到账

原因通常是：

- 用户只完成了扫码但未真正支付确认
- 后端没有收到或没有通过异步回调验签

积分到账必须以异步通知为准。

## 11. 建议

后续可继续补充：

- 管理后台支付订单查询页
- 支付失败原因记录
- 订单关闭逻辑
- 沙箱联调步骤截图
- 生产环境上线核对清单
