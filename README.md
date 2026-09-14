# 🍌 80AI

80AI 是一个面向 Web 管理端、普通用户端、移动端和 API Key 场景的 AI 绘图系统。当前仓库已经覆盖用户注册登录、模板创作、多模式生图、积分体系、兑换码、支付宝在线购买、反馈与系统消息、管理后台、腾讯云 COS 存储，以及独立的对外 API 服务目录。

## 功能总览

### 用户端

- 模板中心：浏览模板、套用模板参数、快速进入创作流程
- AI 生图：支持文生图、图编辑、局部重绘、提示词反推
- 无限画布：支持独立画布项目、画布内生图、自由文本/图片节点、拖拽缩放、节点搜索与一键整理；当前入口仅对管理员、超级管理员和白名单用户开放，便于内部测试
- 批量生图：支持批量卡片配置、全局参数一键应用、按空闲槽位自动排队提交、结果批量下载
- 历史记录：查看任务、预览结果、下载图片、重新生成、删除、置顶
- 账号体系：注册、登录、修改密码、忘记密码、个人资料、头像上传
- 积分体系：余额查询、积分流水、按场景扣费
- 积分获取：兑换码兑换、支付宝积分套餐购买
- 消息与反馈：提交反馈、查看处理结果、查看系统消息
- API Key：用户可创建和管理自己的 API Key，用于程序化调用

### 管理端

- 用户管理：创建用户、启停用户、角色调整、白名单、重置密码、手动充扣积分
- 模板管理：模板及标签维护
- 兑换码管理：批量生成、筛选、启用/禁用
- 数据分析：统计看板、时序分析、维度拆分、兑换码营收
- 全站任务管理：查看用户任务历史与详情
- 反馈处理：查看未处理反馈、更新处理状态
- 系统消息：站内信群发与未读追踪
- 配置管理：公告、联系二维码、COS 配置、外部生图接口配置

### 其他能力

- 腾讯云 COS：前端临时凭证直传，后端结果图上传，兼容历史 `/uploads/...`
- 异步执行：Celery + Redis；开发环境可按配置降级为后台线程
- 支付：已实现支付宝 PC Web 积分购买闭环
- 对外 API：仓库内包含独立 `backend-api/` 服务目录，支持 API Key 场景
- Flutter 客户端：仓库内包含 `flutter_app/`，已实现模板、生图、历史、个人中心等基础能力

## 技术栈

- 前端：Vue 3 + TypeScript + Vite + Ant Design Vue + Pinia + ECharts
- 后端：FastAPI + SQLAlchemy + MySQL + Pydantic Settings
- 异步任务：Celery + Redis
- 存储：腾讯云 COS + STS 临时凭证
- 鉴权与账号辅助能力：JWT + CloudBase 邮箱验证流程
- 移动端：Flutter

## 仓库结构

```text
80AI/
├── frontend/                 # Web 前端
├── backend/                  # 主后端，承载用户端/管理端业务
├── backend-api/              # 面向 API Key 场景的独立后端服务
├── flutter_app/              # Flutter 客户端
├── docs/                     # 运维、接入、用户文档
├── docs-api/                 # 对外 API 文档站点源码与静态站内容
├── prd.md                    # Web 产品需求说明
└── prd-app.md                # Flutter 端需求说明
```

## 角色与权限

- `user`：普通用户，使用创作、历史、支付、反馈、API Key 等功能
- `admin`：管理员，拥有用户管理、模板管理、兑换码、统计、反馈处理等权限
- `superadmin`：超级管理员，额外拥有 COS 配置、外部接口配置、用户状态与角色调整、密码重置等高权限能力
- 无限画布处于内部测试阶段，菜单入口仅在已登录且为 `admin`、`superadmin` 或 `is_whitelisted=true` 时显示

## 快速开始

### 1. 启动后端

```bash
cd backend

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

至少补齐以下数据库配置之一：

- 直接提供 `DATABASE_URL`
- 或提供 `DB_USER`、`DB_PASSWORD`、`DB_NAME`，并按需调整 `DB_HOST`、`DB_PORT`

常用本地开发配置示例：

```env
DB_HOST=sh-cynosdbmysql-grp-kmfw4ojg.sql.tencentcdb.com
DB_PORT=20396
DB_USER=user
DB_PASSWORD=password
DB_NAME=database
DB_CHARSET=utf8mb4
DB_AUTO_CREATE_TABLES=true
DB_RUN_STARTUP_SCHEMA_SYNC=false
DB_RUN_SCHEMA_COMPAT=false
DB_RUN_SEED=false
```

启动服务：

```bash
uvicorn app.main:app --reload --port 8000
```

启动后可访问：

- Swagger 文档：<http://localhost:8000/docs>
- 上传目录静态访问：`/uploads/...`

说明：

- 项目仅支持 MySQL，不再提供 SQLite 回退
- `DB_AUTO_CREATE_TABLES=true` 时会自动建表
- `DB_RUN_STARTUP_SCHEMA_SYNC=true` 时会在启动阶段执行 schema 修复与数据回填；生产环境建议保持关闭，改为上线前手工执行版本化 SQL
- `DB_RUN_SCHEMA_COMPAT=true` 时会在启动阶段补齐兼容字段
- `DB_RUN_SEED=true` 时会初始化默认账号与基础运行配置

如需创建默认账号，请开启 `DB_RUN_SEED=true`，默认值为：

- 超级管理员：`administrator` / `administrator123`
- 管理员：`admin` / `admin123`

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

默认开发地址通常为 <http://localhost:3000>。

前端常用环境变量：

- `VITE_API_BASE_URL`：后端地址
- `VITE_CLOUDBASE_ENV_ID`：CloudBase 环境 ID，用于注册/找回密码的邮箱验证码流程

### 3. 可选：启动 Celery Worker

如果希望使用真实异步队列，而不是开发环境回退逻辑，请先准备 Redis，再启动 Worker：

```bash
cd backend
CELERY_WORKER_CONCURRENCY=4 celery -A app.workers.celery_app worker --loglevel=info
```

说明：

- 仅在 `DEBUG=true` 或 `ALLOW_SYNC_GENERATION_FALLBACK=true` 时，系统才会回退为后台线程执行
- 生产环境不建议依赖线程降级

## 关键业务说明

### 1. 生图与积分

- 任务模式覆盖文生图、图编辑、局部重绘、提示词反推
- 无限画布任务复用普通生图任务链路：同样按场景配置扣费、记录积分流水、执行单用户与全局并发限制；画布任务写入 `tasks.canvas_id`，不会混入普通历史/Board 预览
- 无限画布使用 `user_canvas.project_id` 作为 16 位公开路由标识，前端路由为 `/canvas/:projectId`，不暴露内部自增主键
- Web 端新增 `批量生图` 页面，支持最多 8 张任务卡片连续生成，默认初始化 3 张卡片
- 支持全局模型、尺寸比例、分辨率、自定义尺寸、提示词与参考图一键应用到全部任务卡
- 批量模式下会按当前空闲并发槽位自动提交队列，并轮询任务状态；已完成结果支持预览、下载、删除、继续编辑与反馈
- 图编辑批量模式支持参考图拖拽上传，草稿会保存到浏览器本地，刷新后可恢复上次配置
- 场景、模型、积分单价、参考图上限等由后台外部接口配置管理
- 用户余额保存在 `user_credits` 表，不再使用 `users.credits`
- 积分流水覆盖消费、人工调整、兑换码充值、在线购买等场景

### 2. 支付宝积分购买

当前项目已经完成支付宝 PC Web 支付接入，流程包括：

1. 前端拉取套餐列表
2. 创建本地支付订单
3. 跳转支付宝收银台
4. 接收异步回调并验签
5. 支付成功后为用户发放积分
6. 前端支付结果页轮询订单状态并刷新余额

当前内置套餐示例：

- `starter`：体验包，50 积分
- `light`：轻量体验包，300 积分
- `value`：超值囤货包，1000 积分
- `vip`：至尊畅玩包，2000 积分

后端支付相关环境变量：

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

配置建议：

- `ALIPAY_NOTIFY_URL` 必须是公网 HTTPS 后端地址
- `ALIPAY_RETURN_URL` 应指向前端支付结果页，例如 `https://web.example.com/payment-result`
- 密钥只通过环境变量或 CI Secrets 注入，不要提交到仓库

更详细说明见 `docs/alipay_payment_integration.md`。

### 3. 腾讯云 COS

系统支持将以下资源统一存储到 COS：

- 参考图
- 图编辑与局部重绘的原图、蒙版
- 提示词反推上传图
- 模板图
- AI 生成结果图
- 联系二维码等后台上传资源

配置方式：

1. 使用超级管理员登录后台
2. 进入 `COS 配置` 页面
3. 填写 `Bucket`、`Region`、`SecretId`、`SecretKey`
4. 可选配置自定义访问域名

说明：

- 前端上传会先向后端申请临时凭证，再直传 COS
- 后端会把最终图片地址写回数据库
- 历史本地文件路径仍兼容访问

## 部署建议

### 前端

适合部署到 CloudBase 静态网站托管：

```bash
cd frontend
npm install
npm run build
```

构建后上传 `frontend/dist`，并配置：

- `VITE_API_BASE_URL=https://your-api-domain`
- `VITE_CLOUDBASE_ENV_ID=<your-env-id>`

### 后端

建议拆分为两个服务：

- `Web Service`：承载 API
- `Worker Service`：承载 Celery 生图任务

推荐启动命令：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 80 --workers ${WEB_CONCURRENCY:-2}
```

```bash
celery -A app.workers.celery_app worker --loglevel=info
```

部署时请确保 Web 与 Worker 共享以下配置：

- `DATABASE_URL` 或 `DB_*`
- `REDIS_URL`
- COS 相关配置
- 支付宝相关配置

生产环境建议：

- `DB_RUN_STARTUP_SCHEMA_SYNC=false`
- `DB_RUN_SCHEMA_COMPAT=false`
- `DB_RUN_SEED=false`
- 关闭同步降级模式

推荐发布顺序：

1. 按顺序执行 `docs/sql/migrations/` 下尚未执行过的版本化 SQL。
2. 确认生产库结构已完成本次变更。
3. 再部署 `backend/` 与 `backend-api/`，保持 `DB_RUN_STARTUP_SCHEMA_SYNC=false`。

### 并发起步建议

如果需要先按约 50 个用户并发做起步压测，可从以下参数开始：

- `WEB_CONCURRENCY=2`
- `CELERY_WORKER_CONCURRENCY=6`
- `DB_POOL_SIZE=10`
- `DB_MAX_OVERFLOW=20`
- `CELERY_PREFETCH_MULTIPLIER=1`
- `MAX_ACTIVE_TASKS_PER_USER=5`
- `MAX_ACTIVE_TASKS_GLOBAL=500`

最终参数请以真实压测结果为准。

## API 概览

### 用户侧核心接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/forgot-password` | 邮箱验证码重置密码 |
| GET | `/api/auth/me` | 当前用户信息 |
| PUT | `/api/auth/profile` | 修改个人资料 |
| POST | `/api/auth/redeem-key` | 兑换积分码 |
| GET | `/api/auth/credit-logs` | 我的积分流水 |
| GET | `/api/auth/prompt-history` | 最近提示词历史 |
| POST | `/api/tasks` | 创建任务 |
| GET | `/api/history` | 我的历史任务 |
| POST | `/api/upload` | 普通上传 |
| POST | `/api/upload/credential` | 获取 COS 临时凭证 |
| GET | `/api/payment/plans` | 获取积分套餐 |
| POST | `/api/payment/orders` | 创建支付订单 |
| GET | `/api/payment/orders/{order_no}` | 查询支付订单 |
| POST | `/api/feedback` | 提交反馈 |
| GET | `/api/system-messages` | 查看系统消息 |
| GET | `/api/user-api-keys` | 查看我的 API Key |

### 管理侧核心接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/admin/users` | 创建用户 |
| GET | `/api/admin/users` | 用户列表 |
| PUT | `/api/admin/users/{user_id}/status` | 启用/禁用用户 |
| PUT | `/api/admin/users/{user_id}/role` | 修改角色 |
| POST | `/api/admin/users/{user_id}/credits` | 手动调整积分 |
| POST | `/api/admin/redeem-keys/batch` | 批量生成兑换码 |
| GET | `/api/admin/stats` | 基础统计 |
| GET | `/api/admin/analytics/summary` | 汇总分析 |
| GET | `/api/admin/analytics/timeseries` | 时序分析 |
| GET | `/api/admin/history` | 全站任务历史 |
| GET | `/api/admin/feedbacks` | 反馈管理 |
| GET | `/api/admin/system-messages` | 系统消息管理 |

### 支付回调接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/payment/return/alipay` | 支付完成后回跳前端结果页 |
| POST | `/api/payment/webhook/alipay` | 支付宝异步回调 |

完整接口说明请以运行后的 Swagger 为准：<http://localhost:8000/docs>

## 文档索引

- `docs/web_user_guide.md`：Web 端用户使用说明
- `docs/alipay_payment_integration.md`：支付宝支付接入说明
- `docs/mysql_empty_database_init.md`：MySQL 空库初始化说明
- `docs/sql/migrations/README.md`：数据库版本化 SQL 迁移说明
- `docs/backend-security-checklist.md`：后端安全检查清单
- `docs/user_agreement.md`：用户协议
- `docs/privacy_policy.md`：隐私政策

## 说明

- `backend-api/` 是独立的 API 服务目录，适合 API Key / 第三方接入场景
- `flutter_app/` 是移动端工程，功能覆盖以其当前代码实现为准，不与 Web 完全等同
- `docs-api/` 用于维护独立的开发者 API 文档站点
