# 🧾 80AI — 产品需求文档

> 面向创意模版、AI 生图、局部重绘、提示词反推的一体化绘图系统
> 最后更新：2026-04-12

---

# 一、技术架构

## 1.1 技术栈


| 层     | 技术                                                         |
| ----- | ---------------------------------------------------------- |
| 前端    | Vue 3 + TypeScript + Vue Router + Pinia + Ant Design Vue 4 |
| 后端    | FastAPI + SQLAlchemy 2.0 + MySQL                              |
| AI 能力 | Gemini（文生图 / 图编辑 / 局部重绘）、通义千问 Qwen-VL（提示词反推）               |
| 异步任务  | Celery + Redis（可选，无 Redis 自动降级为后台线程）                       |
| 部署    | 前端 Vercel / 后端 VPS 或 Railway                               |


## 1.2 项目结构

```text
80AI/
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   ├── auth.ts
│   │   │   ├── tasks.ts
│   │   │   ├── images.ts
│   │   │   ├── upload.ts
│   │   │   ├── templates.ts
│   │   │   ├── promptReverse.ts
│   │   │   ├── admin.ts
│   │   │   ├── config.ts
│   │   │   └── client.ts
│   │   ├── components/
│   │   │   ├── generate/RepaintCanvas.vue
│   │   │   └── layout/AppLayout.vue
│   │   ├── views/
│   │   │   ├── TemplatesView.vue
│   │   │   ├── GenerateView.vue
│   │   │   ├── HistoryView.vue
│   │   │   ├── CreditLogsView.vue
│   │   │   └── admin/
│   │   │       ├── UserManageView.vue
│   │   │       ├── DashboardView.vue
│   │   │       ├── TemplateManageView.vue
│   │   │       ├── ApiKeyView.vue
│   │   │       └── ExternalApiConfigView.vue
│   │   ├── stores/auth.ts
│   │   ├── router/index.ts
│   │   ├── types/index.ts
│   │   └── composables/usePolling.ts
│   └── vercel.json
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py
│   │   │   ├── tasks.py
│   │   │   ├── images.py
│   │   │   ├── history.py
│   │   │   ├── upload.py
│   │   │   ├── templates.py
│   │   │   ├── prompt_reverse.py
│   │   │   ├── admin.py
│   │   │   ├── api_key.py
│   │   │   ├── external_api_config.py
│   │   │   └── deps.py
│   │   ├── models/
│   │   │   ├── user.py
│   │   │   ├── task.py
│   │   │   ├── image.py
│   │   │   ├── credit_log.py
│   │   │   ├── prompt_history.py
│   │   │   ├── template.py
│   │   │   ├── template_tag.py
│   │   │   ├── template_tag_relation.py
│   │   │   ├── external_api_config.py
│   │   │   ├── external_api_scene_binding.py
│   │   │   └── api_key.py
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── workers/generation.py
│   │   ├── static/error.svg
│   │   ├── utils/security.py
│   │   ├── config.py
│   │   ├── database.py
│   │   └── main.py
│   ├── data/
│   ├── uploads/
│   └── requirements.txt
└── prd.md
```

---

# 二、系统模块划分

系统当前分为 8 大模块：

1. **认证与账户模块** — 登录 / 注册 / 修改密码 / JWT / 头像上传
2. **创意模版模块** — 默认首页、标签筛选、模版详情、模版带入生成页
3. **自定义绘图模块** — 文生图 / 图编辑、局部重绘、提示词反推
4. **无限画布模块** — 独立画布项目、画布内生图、节点拖拽缩放、自由节点、节点搜索与整理
5. **历史记录模块** — 历史任务浏览、删除、重新编辑、历史提示词
6. **积分系统模块** — 积分分配、消耗、日志、顶部余额展示
7. **后台管理模块** — 用户管理、数据统计、模版管理、配置管理、外部接口与场景绑定管理
8. **AI 能力引擎** — Gemini 生图链路、Qwen-VL 提示词反推链路

---

# 三、认证与账户模块

## 3.1 功能说明

- 无独立登录页，登录 / 注册在顶部弹窗内完成
- 支持用户注册、登录、修改密码、上传头像
- Token 默认有效期 24 小时
- 未登录用户可浏览首页与模版详情
- 以下动作必须登录：
  - 上传图片
  - 开始生成
  - 局部重绘
  - 提示词反推
  - 打开历史记录
  - 打开历史提示词
- 若登录态过期，前端在用户点击上传 / 生成等动作前会校验会话，失效则弹出登录框

## 3.2 角色说明


| 角色    | 功能                                                 |
| ----- | -------------------------------------------------- |
| 普通用户  | 注册、登录、修改密码、上传头像、使用模版、生成图片、查看自己的历史与积分               |
| 白名单用户 | 拥有普通用户能力，并可在内部测试阶段看到并使用无限画布入口                         |
| 管理员   | 拥有普通用户全部能力，另可分配积分、管理模板、维护配置、查看统计，并可使用无限画布内部测试入口 |
| 超级管理员 | 拥有管理员能力，且可创建用户、设置角色、启用/禁用用户、重置用户密码、访问 COS 配置页与接口管理 |


## 3.3 顶部账户区

- 已登录时显示：积分余额、头像、用户名
- 点击积分余额：打开“联系我们获取积分”弹窗
- 弹窗展示：
  - 文案：`积分获取、api调用、技术支持、其他业务需求定制`
  - 后台可配置联系二维码

---

# 四、创意模版模块

## 4.1 首页定位

- 默认首页为 `创意模版`
- 路由 `/` 默认跳转到 `/templates`
- 模版页支持未登录浏览

## 4.2 用户侧能力

- 标签筛选（不包裹额外 card）
- 模版 5 列瀑布 / 网格展示
- 模版卡片仅展示结果图
- Hover 显示“查看详情”
- 点击卡片后打开详情弹窗
- 详情中可查看：
  - 结果图
  - 提示词
  - 参考图
  - 宽高比
  - 分辨率
  - 标签
- 模版默认按单张使用，不展示生图数量
- 详情弹窗底部仅保留“使用此模版”主操作，不展示额外关闭按钮
- 点击“使用此模版”后仅回填到生成页，不自动提交任务

## 4.3 管理侧能力

- 新增、编辑、删除模版
- 模版字段：
  - 提示词
  - 参考图片（可选，多张）
  - 结果图
  - 模型
  - 宽高比
  - 分辨率
  - 图片数量固定为 `1`，不提供编辑
  - 多选标签

---

# 五、自定义绘图模块

## 5.1 页面布局

- 页面路由：`/generate`
- 整体为左右双栏布局，宽度比例接近黄金分割
- 左侧为配置区，右侧为结果区
- 左侧顶部使用 Tabs，当前共 3 个 tab：
  - `文生图/图编辑`
  - `提示词反推`
  - `局部重绘`

## 5.2 文生图 / 图编辑

### 能力

- 提示词输入
- 固定 4 种模型选择：
  - `banana`
  - `banana2`
  - `banana_pro`
  - `banana_pro_plus`
- 历史提示词弹窗（最近 10 条，可删除、可回填）
- 参考图上传（最多 6 张）
- 图片数量 slider（1-6）
- 宽高比选择
- 分辨率选择
- 开始生成按钮内直接显示积分消耗

### 生成规则

- 每张图片消耗由当前模型场景配置决定，总费用 = 场景单价 × 生成张数
- 支持参考图辅助生成
- 运行时按所选模型场景查找后台绑定接口
- `banana` 模型不显示分辨率选项
- 支持任务轮询
- 结果支持：
  - 预览
  - 下载
  - 单张重新生成

## 5.3 提示词反推

### 目标

- 用户上传一张图片
- 调用后台绑定的 `prompt_reverse` 场景接口
- 返回适合 AI 绘画使用的**中文提示词**

### 交互

- 上传图片
- 点击“开始反推 · X 积分”
- 返回中文提示词结果
- 支持：
  - 复制提示词
  - 一键带入“文生图/图编辑”tab

### 积分规则

- 每次提示词反推消耗由 `prompt_reverse` 场景积分配置决定

## 5.4 局部重绘

### 目标

- 用户上传原图
- 在图片上涂抹需要修改的局部区域
- 系统生成蒙版并调用 AI 完成局部重绘

### 交互

- 绘制区域位于提示词输入框上方
- 支持工具栏：
  - 涂抹
  - 擦除
  - 画笔大小调整
  - 画笔圆点预览
  - 清空选区
  - 撤销
  - 重做
- 图片右上角提供 `X` 按钮移除原图
- 前端显示的蒙层透明度为 `50%`
- 导出给后端的蒙版仍为纯黑白图，不携带透明度

### 生成规则

- 局部重绘按单张任务处理
- 每次局部重绘消耗由 `inpaint` 场景积分配置决定
- 运行时固定使用后台 `inpaint` 场景绑定接口，用户不选择模型
- 提交时必须同时具备：
  - 原图
  - 提示词
  - 蒙版选区

## 5.5 结果区

- 文生图 / 图编辑、局部重绘共用右侧图片结果区
- 提示词反推结果在当前 tab 内展示，不复用右侧图片区
- 当不同 tab 激活时，空状态文案会根据模式变化

## 5.6 无限画布

### 入口与权限

- 路由入口：`/canvas`
- 工作台路由：`/canvas/:projectId`
- `projectId` 为 16 位字母数字公开 ID，不使用数据库自增主键作为 URL
- 当前处于内部测试阶段，顶部菜单仅对已登录的管理员、超级管理员和白名单用户显示
- 从工作台返回画布列表时，不自动跳回单个画布；直接访问 `/canvas` 且仅有一个画布时可自动进入该画布工作台

### 画布项目

- 每个用户可创建多个画布项目
- 画布列表展示画布名称、节点数量、最近预览图和更新时间
- 工作台左上角使用下拉按钮展示当前画布，可切换、重命名、新建画布
- 每个画布保存独立视口位置和缩放比例

### 节点能力

- 任务节点：由画布内生图任务生成，展示任务状态、生成图、失败信息、任务操作工具栏
- 文本节点：可作为自由创意备注，支持编辑、生成图片、删除
- 图片节点：支持本地上传，按真实宽高比展示，支持作为参考图继续编辑
- 节点支持拖拽、缩放、删除、双击预览或编辑
- 支持搜索节点并聚焦到 100% 缩放位置
- 支持一键整理，将文本节点、上传图片节点、任务节点分组横向排布

### 画布内生图

- 底部配置卡片支持文生图和图编辑模式，默认图编辑
- 图编辑参考图可本地上传、拖拽上传，也可从画布已有图片中多选
- 参考图数量遵循当前模型 `max_reference_images` 限制
- 生成按钮展示预计消耗积分，点击剩余积分可打开购买积分弹窗
- 画布任务复用普通生图任务链路，统一进行积分扣减、积分不足提示、单用户与全局并发限制、任务入队失败退款
- 画布任务写入 `tasks.canvas_id`，历史/Board 默认预览不展示画布专属任务

---

# 六、历史记录模块

## 6.1 历史任务页

- 路由：`/history`
- 以结果图卡片流展示用户历史记录
- 支持按任务类型筛选：`生图`、`局部重绘`
- 支持按模型筛选
- 支持按任务状态筛选：`等待中`、`处理中`、`成功`、`失败`
- 支持按提示词关键词筛选
- 支持按时间范围筛选
- 每张结果图对应一张历史卡片
- 卡片主视图仅展示：
  - 结果图
  - 类型
  - 状态
  - 时间
- 提示词、尺寸、分辨率、参考图等参数在详情弹窗展示

## 6.2 操作能力

- 查看大图
- 下载结果
- 删除单张结果图
- 重新编辑
- 查看详情弹窗

## 6.3 重新编辑

- 点击“重新编辑”后跳回 `/generate`
- 自动回填：
  - 文生图：模型、提示词、参考图、宽高比、分辨率、图片数量
  - 局部重绘：提示词、原图、宽高比、分辨率
- 局部重绘重新编辑时自动切到“局部重绘”tab
- 不回填旧蒙版，用户需重新涂抹
- 仅回填，不自动发起任务

## 6.4 历史提示词

- 在生成页内单独维护最近 10 次提示词历史
- 支持：
  - 列表查看
  - 单条删除
  - 点击回填当前提示词输入框

---

# 七、积分系统模块

## 7.1 账户余额

- 用户登录后，右上角显示剩余积分
- 样式为文本式展示，不与头像合并为一个按钮
- 点击后打开联系弹窗，不跳转积分日志页

## 7.2 消费规则


| 功能        | 消耗                               |
| --------- | -------------------------------- |
| 文生图 / 图编辑 | 按所选模型场景配置的积分单价按张扣费               |
| 局部重绘      | 按 `inpaint` 场景配置的固定积分按次扣费        |
| 提示词反推     | 按 `prompt_reverse` 场景配置的固定积分按次扣费 |


## 7.3 管理员能力

- 普通管理员在用户管理中仅可为用户分配积分
- 支持填写数量与说明
- 自动记录积分分配日志

## 7.4 日志能力

- 普通用户可查看自己的积分记录
- 管理员可查看全部积分记录
- 支持按用户、时间筛选
- 日志包含：
  - 分配记录
  - 图片生成消耗
  - 提示词反推消耗

---

# 八、后台管理模块

## 8.1 用户管理

- 用户列表字段：
  - ID
  - 用户名
  - 头像
  - 角色
  - 状态
  - 积分
  - 创建时间
- 支持：
  - 查看用户列表（管理员 / 超级管理员）
  - 分配积分
  - 创建用户（仅超级管理员）
  - 启用 / 禁用（仅超级管理员）
  - 设置角色（仅超级管理员）
  - 重置密码（仅超级管理员）

## 8.2 数据统计

- 最近 7 / 30 天生成量
- 总用户数
- 活跃用户数

## 8.3 模版管理

- 管理创意模版 CRUD
- 管理标签
- 维护结果图与参考图
- 模版数量固定为 `1`

## 8.4 配置管理

后台“配置管理”页统一维护全局配置：

- Gemini API Key
- Tongyi API Key
- 联系二维码图片

要求：

- 支持查看（掩码）、编辑、复制、删除
- 配置存数据库，后端动态读取
- 修改后无需重启服务

## 8.5 COS 配置页

超级管理员可进入独立“COS 配置”页，页面只维护：

- `SecretId`
- `SecretKey`
- `Bucket`
- `Region`
- 可选访问域名

要求：

- 仅超级管理员可访问
- 支持查看（掩码）、编辑、复制、清空
- 配置存数据库，后端动态读取
- 修改后无需重启服务
- 图片存储接入腾讯云 COS：
  - 前端上传参考图、局部重绘原图/蒙版、二维码、模版图时，先向后端获取临时凭证，再直传 COS
  - 后端生成结果图后直接上传到 COS
  - 数据库中统一记录上传后的公网 URL

## 8.6 外部接口管理

超级管理员可进入独立“接口管理”页，页面拆为两个区域：

### 接口配置区

- 维护接口名称
- 维护分组 `group_name`
- 维护请求地址
- 维护 Header JSON
- 维护请求 JSON
- 启用 / 停用
- 测试连接

### 场景绑定区

固定维护以下 6 个调用场景：

- `banana`
- `banana2`
- `banana_pro`
- `banana_pro_plus`
- `prompt_reverse`
- `inpaint`

规则：

- 每个场景单独绑定一个接口
- 一个接口可以被多个场景复用
- 每个场景单独配置积分消耗 `credit_cost`
- 可按分组筛选接口
- 分组仅用于展示和筛选，不参与运行时逻辑

---

# 九、AI 能力引擎

## 9.1 Gemini 生图链路

用于：

- 文生图 / 图编辑
- 局部重绘

### 配置

- 生图实际接口配置来源：数据库 `external_api_configs`
- 生图实际场景绑定来源：数据库 `external_api_scene_bindings`
- 默认迁移种子可由 `AI_API_URL` 与 `api_keys.key` 初始化
- 超时：`AI_TIMEOUT`

### 调用方式

- 文生图 / 图编辑：
  - 可带多张参考图
  - 按 `banana / banana2 / banana_pro / banana_pro_plus` 场景选接口
  - 返回图片结果
- 局部重绘：
  - 固定走 `inpaint` 场景绑定
  - 传入原图 + 蒙版 + 提示词
  - 要求仅修改白色蒙版区域

### 失败策略

- 调用失败或超时时，图片状态置为 `failed`
- 使用统一静态错误图 `error.svg`

## 9.2 通义千问提示词反推链路

用于：

- `提示词反推` tab

### 配置

- 反推实际接口配置来源：数据库 `external_api_configs`
- 反推实际场景绑定来源：数据库 `external_api_scene_bindings`
- 默认迁移种子可由 `api_keys.tongyi_key` 初始化

### 调用方式

- 上传图片后，若为 COS 公网 URL，则由后端拉取远程图片并转为 base64 data URL；历史本地 `/uploads/...` 路径仍兼容
- 固定走 `prompt_reverse` 场景绑定
- 模型：`qwen-vl-plus`
- 固定提示词：要求输出适合 AI 绘画使用的**中文提示词**

---

# 十、数据库结构

## 10.1 用户表（users）

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username VARCHAR(50) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(20) DEFAULT 'user',
  status VARCHAR(20) DEFAULT 'active',
  avatar_url VARCHAR(500) DEFAULT '',
  credits INTEGER NOT NULL DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 10.2 生成任务表（tasks）

```sql
CREATE TABLE tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  model VARCHAR(50) DEFAULT '',
  mode VARCHAR(20) DEFAULT 'generate',       -- generate | inpaint
  prompt TEXT NOT NULL DEFAULT '',
  num_images INTEGER DEFAULT 4,
  size VARCHAR(20) DEFAULT '3:4',
  resolution VARCHAR(10) DEFAULT '4K',
  reference_image VARCHAR(500) DEFAULT '',
  reference_images TEXT DEFAULT '',          -- JSON array
  source_image VARCHAR(500) DEFAULT '',
  mask_image VARCHAR(500) DEFAULT '',
  canvas_id INTEGER,                         -- 关联无限画布；为空表示普通任务
  status VARCHAR(20) DEFAULT 'pending',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
```

## 10.2.1 用户画布表（user_canvas）

```sql
CREATE TABLE user_canvas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id VARCHAR(16) NOT NULL UNIQUE,
  user_id INTEGER NOT NULL,
  name VARCHAR(100) NOT NULL DEFAULT '',
  viewport_x DOUBLE NOT NULL DEFAULT 0,
  viewport_y DOUBLE NOT NULL DEFAULT 0,
  zoom DOUBLE NOT NULL DEFAULT 1,
  is_deleted BOOLEAN NOT NULL DEFAULT 0,
  deleted_at DATETIME,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
```

说明：

- `project_id` 用于 `/canvas/:projectId` 路由，避免暴露内部自增主键。
- `viewport_x`、`viewport_y`、`zoom` 保存用户在该画布中的视口状态。
- 删除画布时使用逻辑删除，便于后续审计和恢复策略扩展。

## 10.2.2 画布节点表（canvas_nodes）

```sql
CREATE TABLE canvas_nodes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canvas_id INTEGER NOT NULL,
  task_id INTEGER,
  node_type VARCHAR(20) NOT NULL DEFAULT 'task',
  content VARCHAR(5000) NOT NULL DEFAULT '',
  image_url VARCHAR(1000) NOT NULL DEFAULT '',
  x DOUBLE NOT NULL DEFAULT 0,
  y DOUBLE NOT NULL DEFAULT 0,
  width DOUBLE NOT NULL DEFAULT 320,
  height DOUBLE NOT NULL DEFAULT 420,
  z_index INTEGER NOT NULL DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (canvas_id) REFERENCES user_canvas(id),
  FOREIGN KEY (task_id) REFERENCES tasks(id)
);
```

说明：

- `node_type='task'` 表示任务节点，`task_id` 必填。
- `node_type='text'` 表示自由文本节点，内容写入 `content`。
- `node_type='image'` 表示上传图片节点，图片地址写入 `image_url`。
- 节点位置、尺寸、层级由前端工作台写回，支持批量更新。

## 10.3 图片结果表（images）

```sql
CREATE TABLE images (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL,
  image_url VARCHAR(255) DEFAULT '',
  status VARCHAR(20) DEFAULT 'pending',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (task_id) REFERENCES tasks(id)
);
```

## 10.4 重新生成记录表（regenerate_logs）

```sql
CREATE TABLE regenerate_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  image_id INTEGER NOT NULL,
  old_image_url VARCHAR(255) DEFAULT '',
  new_image_url VARCHAR(255) DEFAULT '',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (image_id) REFERENCES images(id)
);
```

## 10.5 积分日志表（credit_logs）

```sql
CREATE TABLE credit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  amount INTEGER NOT NULL,
  type VARCHAR(20) NOT NULL,                 -- allocate | consume
  description VARCHAR(500) DEFAULT '',
  operator_id INTEGER,
  task_id INTEGER,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 10.6 历史提示词表（prompt_history）

```sql
CREATE TABLE prompt_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  prompt TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 10.7 创意模版表（templates）

```sql
CREATE TABLE templates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  prompt TEXT NOT NULL,
  model VARCHAR(50) DEFAULT 'banana_pro',
  reference_images TEXT DEFAULT '',          -- JSON array
  num_images INTEGER DEFAULT 1,
  size VARCHAR(20) DEFAULT '1:1',
  resolution VARCHAR(10) DEFAULT '2K',
  result_image VARCHAR(500) DEFAULT '',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 10.8 模版标签表（template_tags / template_tag_relations）

```sql
CREATE TABLE template_tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(100) NOT NULL UNIQUE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE template_tag_relations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  template_id INTEGER NOT NULL,
  tag_id INTEGER NOT NULL
);
```

## 10.9 配置表（api_keys）

```sql
CREATE TABLE api_keys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key VARCHAR(255) NOT NULL DEFAULT '',            -- Gemini API Key
  tongyi_key VARCHAR(255) NOT NULL DEFAULT '',    -- Tongyi API Key
  contact_qr_image VARCHAR(500) NOT NULL DEFAULT '',
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 10.10 外部接口配置表（external_api_configs）

```sql
CREATE TABLE external_api_configs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(100) NOT NULL UNIQUE,
  description VARCHAR(255) NOT NULL DEFAULT '',
  group_name VARCHAR(100) NOT NULL DEFAULT '默认',
  request_url VARCHAR(500) NOT NULL DEFAULT '',
  headers_json TEXT NOT NULL DEFAULT '{}',
  payload_json TEXT NOT NULL DEFAULT '{}',
  status VARCHAR(20) NOT NULL DEFAULT 'enabled',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

说明：

- 该表以“纯接口配置”为主
- 只维护接口本身信息，不直接决定调用场景

## 10.11 外部接口场景绑定表（external_api_scene_bindings）

```sql
CREATE TABLE external_api_scene_bindings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scene_key VARCHAR(50) NOT NULL UNIQUE,
  api_config_id INTEGER,
  credit_cost INTEGER NOT NULL DEFAULT 0,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (api_config_id) REFERENCES external_api_configs(id)
);
```

说明：

- 每个 `scene_key` 只能绑定一个接口
- 一个接口可被多个场景复用
- 每个 `scene_key` 独立维护一份积分配置
- 当前固定场景为 `banana`、`banana2`、`banana_pro`、`banana_pro_plus`、`prompt_reverse`、`inpaint`

---

# 十一、API 接口文档

## 11.1 认证与账户


| 方法     | 路径                             | 权限  | 说明             |
| ------ | ------------------------------ | --- | -------------- |
| POST   | `/api/auth/register`           | 公开  | 用户注册           |
| POST   | `/api/auth/login`              | 公开  | 登录             |
| POST   | `/api/auth/change-password`    | 用户  | 修改密码           |
| GET    | `/api/auth/me`                 | 用户  | 获取当前用户         |
| POST   | `/api/auth/avatar`             | 用户  | 上传头像           |
| GET    | `/api/auth/prompt-history`     | 用户  | 获取最近 10 条历史提示词 |
| DELETE | `/api/auth/prompt-history/:id` | 用户  | 删除历史提示词        |
| GET    | `/api/auth/credit-logs`        | 用户  | 获取积分记录         |


## 11.2 生成任务


| 方法   | 路径               | 权限  | 说明            |
| ---- | ---------------- | --- | ------------- |
| POST | `/api/tasks`     | 用户  | 创建生图 / 局部重绘任务 |
| GET  | `/api/tasks/:id` | 用户  | 查询任务结果        |

### 创建任务请求示例

```json
{
  "mode": "generate",
  "model": "banana_pro",
  "prompt": "一只在花园中奔跑的金毛犬",
  "num_images": 4,
  "size": "3:4",
  "resolution": "4K",
  "reference_images": ["/uploads/ref/a.jpg", "/uploads/ref/b.jpg"]
}
```

局部重绘示例：

```json
{
  "mode": "inpaint",
  "prompt": "将遮罩区域替换为更明亮的花朵细节",
  "num_images": 1,
  "size": "3:4",
  "resolution": "2K",
  "source_image": "/uploads/source.jpg",
  "mask_image": "/uploads/mask.png"
}
```

## 11.2.1 无限画布接口

| 方法     | 路径                                      | 权限 | 说明                         |
| ------ | ----------------------------------------- | ---- | ---------------------------- |
| GET    | `/api/canvases`                           | 用户 | 获取当前用户画布列表         |
| POST   | `/api/canvases`                           | 用户 | 新建画布                     |
| GET    | `/api/canvases/:projectId`                | 用户 | 获取画布详情和节点           |
| PATCH  | `/api/canvases/:projectId`                | 用户 | 更新画布名称或视口           |
| POST   | `/api/canvases/:projectId/tasks`          | 用户 | 在画布中创建生图任务         |
| POST   | `/api/canvases/:projectId/nodes`          | 用户 | 创建自由文本或上传图片节点   |
| PATCH  | `/api/canvases/:projectId/nodes/:nodeId`  | 用户 | 更新单个节点位置、尺寸或内容 |
| PATCH  | `/api/canvases/:projectId/nodes/batch`    | 用户 | 批量更新节点位置、尺寸、层级 |
| DELETE | `/api/canvases/:projectId/nodes/:nodeId`  | 用户 | 删除自由节点                 |

说明：

- `projectId` 对应 `user_canvas.project_id`，不是内部自增 ID。
- 画布内创建任务复用 `/api/tasks` 的积分扣减、并发限制、任务分发和失败退款逻辑。
- 画布任务通过 `tasks.canvas_id` 与画布关联，默认不进入普通 Board 预览。

## 11.3 提示词反推


| 方法   | 路径                    | 权限  | 说明            |
| ---- | --------------------- | --- | ------------- |
| POST | `/api/prompt-reverse` | 用户  | 根据图片反推中文绘画提示词 |


请求：

```json
{ "image_url": "/uploads/example.jpg" }
```

响应：

```json
{ "prompt": "主体，风格，构图，光影，色彩，画质，细节" }
```

## 11.4 图片接口


| 方法     | 路径                           | 权限  | 说明                    |
| ------ | ---------------------------- | --- | --------------------- |
| POST   | `/api/images/:id/regenerate` | 用户  | 单张重新生成                |
| GET    | `/api/images/:id/download`   | 用户  | 下载图片                  |
| DELETE | `/api/images/:id`            | 用户  | 删除单张历史结果图，若任务已空则清理空任务 |


## 11.5 上传接口


| 方法   | 路径                       | 权限  | 说明                                                      |
| ---- | ------------------------ | --- | ------------------------------------------------------- |
| POST | `/api/upload`            | 用户  | 上传图片（JPG/PNG/WEBP/GIF，≤10MB）                            |
| POST | `/api/upload/credential` | 用户  | 获取腾讯云 COS 临时上传凭证，返回 `bucket`、`region`、`key`、临时密钥与最终 URL |


## 11.6 历史记录接口


| 方法  | 路径             | 权限  | 说明                                                                           |
| --- | -------------- | --- | ---------------------------------------------------------------------------- |
| GET | `/api/history` | 用户  | 获取按结果图展开的历史记录，支持 `mode`、`model`、`prompt`、`status`、`start_date`、`end_date` 筛选 |


## 11.7 创意模版接口


| 方法     | 路径                          | 权限  | 说明               |
| ------ | --------------------------- | --- | ---------------- |
| GET    | `/api/templates`            | 公开  | 获取模板列表           |
| GET    | `/api/templates/tags`       | 公开  | 获取模板标签           |
| GET    | `/api/templates/:id`        | 公开  | 获取模板详情           |
| GET    | `/api/templates/admin/list` | 管理员 | 管理端模板列表          |
| POST   | `/api/templates`            | 管理员 | 创建模板，生图数量固定为 `1` |
| PUT    | `/api/templates/:id`        | 管理员 | 编辑模板，生图数量固定为 `1` |
| DELETE | `/api/templates/:id`        | 管理员 | 删除模板             |


## 11.8 管理员接口


| 方法     | 路径                                                  | 权限    | 说明                                   |
| ------ | --------------------------------------------------- | ----- | ------------------------------------ |
| POST   | `/api/admin/users`                                  | 超级管理员 | 创建用户                                 |
| GET    | `/api/admin/users`                                  | 管理员   | 用户列表                                 |
| PUT    | `/api/admin/users/:id/status`                       | 超级管理员 | 禁用 / 启用                              |
| PUT    | `/api/admin/users/:id/role`                         | 超级管理员 | 设置角色                                 |
| PUT    | `/api/admin/users/:id/reset-password`               | 超级管理员 | 重置密码                                 |
| POST   | `/api/admin/users/:id/credits`                      | 管理员   | 分配积分                                 |
| GET    | `/api/admin/credit-logs`                            | 管理员   | 获取积分日志                               |
| GET    | `/api/admin/stats`                                  | 管理员   | 数据统计                                 |
| GET    | `/api/admin/history`                                | 管理员   | 全部生成记录                               |
| GET    | `/api/admin/api-key`                                | 管理员   | 获取普通配置（Gemini / Tongyi / 联系二维码 / 公告） |
| PUT    | `/api/admin/api-key`                                | 管理员   | 保存普通配置                               |
| DELETE | `/api/admin/api-key`                                | 管理员   | 清空普通配置                               |
| GET    | `/api/admin/cos-config`                             | 超级管理员 | 获取 COS 配置                            |
| PUT    | `/api/admin/cos-config`                             | 超级管理员 | 保存 COS 配置                            |
| DELETE | `/api/admin/cos-config`                             | 超级管理员 | 清空 COS 配置                            |
| GET    | `/api/admin/external-api-configs`                   | 超级管理员 | 获取外部接口配置列表                           |
| POST   | `/api/admin/external-api-configs`                   | 超级管理员 | 新增外部接口配置                             |
| PUT    | `/api/admin/external-api-configs/:id`               | 超级管理员 | 编辑外部接口配置                             |
| PATCH  | `/api/admin/external-api-configs/:id/status`        | 超级管理员 | 启用 / 停用外部接口配置                        |
| POST   | `/api/admin/external-api-configs/test`              | 超级管理员 | 测试接口连接                               |
| GET    | `/api/admin/external-api-scene-bindings`            | 超级管理员 | 获取场景绑定列表                             |
| PUT    | `/api/admin/external-api-scene-bindings/:scene_key` | 超级管理员 | 更新场景绑定与积分                            |


## 11.9 公开配置接口


| 方法  | 路径                              | 权限  | 说明              |
| --- | ------------------------------- | --- | --------------- |
| GET | `/api/config/contact`           | 公开  | 获取联系二维码配置       |
| GET | `/api/config/generation-models` | 公开  | 获取固定四模型展示配置     |
| GET | `/api/config/task-scenes`       | 公开  | 获取各调用场景的积分与展示配置 |


---

# 十二、前端页面说明

## 12.1 顶部导航

- 菜单：
  - 创意模版
  - 自定义绘图
  - 无限画布（内部测试，仅管理员、超级管理员、白名单用户可见）
  - 历史记录
- 已登录：
  - 左侧显示积分余额
  - 右侧显示头像与用户名
  - 下拉菜单提供头像上传、修改密码、积分记录、退出登录
- 管理员额外可进入：
  - 用户管理
  - 数据统计
  - 模版管理
  - 配置管理
  - COS 配置（超级管理员）
  - 接口管理（超级管理员）

## 12.2 创意模版页

- 5 列模板瀑布 / 网格
- Hover 查看详情
- 详情弹窗支持模板带入生成页
- 模版默认单张使用，不展示生图数量
- 详情弹窗底部仅保留“使用此模版”

## 12.3 自定义绘图页

- `文生图/图编辑`
- `提示词反推`
- `局部重绘`
- 文生图固定 4 个模型选项
- `banana` 不显示分辨率
- 局部重绘不让用户选模型，由后台绑定接口决定
- 按钮积分文案与前端余额校验均读取后台场景积分配置

上传图片、开始生成、开始反推等动作均要求已登录；未登录或会话失效会直接弹登录框。

## 12.4 无限画布页

- `/canvas` 展示画布列表，支持新建、重命名、删除/隐藏、点击进入工作台
- `/canvas/:projectId` 为独立工作台，隐藏顶部主菜单，右上角展示剩余积分和返回画布列表入口
- 左上角画布名称使用下拉按钮展示，可切换其他画布、重命名当前画布或新建画布
- 工作台支持鼠标滚轮缩放、拖拽平移、节点拖动、节点缩放、双击预览图片或编辑文本
- 底部配置卡片支持文生图/图编辑切换、参考图上传/画布选择、模型/比例/分辨率/数量配置
- 点击画布空白处时，若配置卡片没有提示词或参考图则自动收起；存在草稿内容时保持展开
- 左侧工具栏提供自由节点、搜索节点、历史任务入口；当前自由节点和搜索节点已实现
- 右上角剩余积分按钮可打开购买积分弹窗

## 12.5 历史记录页

- 支持查看、删除、重新编辑
- 支持按生图 / 局部重绘分类筛选
- 支持按模型筛选
- 支持按任务状态筛选
- 支持按提示词关键词筛选
- 支持按时间范围筛选
- 顶部总览改为轻量信息条，不抢占主要视觉空间
- 列表主视图只突出结果图卡片，详情通过弹窗查看
- 删除操作按单张结果图执行，而不是整任务
- 局部重绘历史重新编辑会直接进入局部重绘模式

## 12.6 配置管理页

- Gemini API Key
- Tongyi API Key
- 联系二维码上传与预览

## 12.7 COS 配置页

- 仅超级管理员可访问
- 独立菜单入口，不与普通配置管理页混用
- 包含 `SecretId`、`SecretKey`、`Bucket`、`Region`、可选访问域名
- 支持保存与清空

## 12.8 接口管理页

- 仅超级管理员可访问
- 分为“接口配置”和“场景绑定”两个区域
- 接口配置支持新增、编辑、分组、启停、测试连接
- 场景绑定固定列出 6 个场景
- 每个场景可同时维护绑定接口和积分消耗
- 可按接口分组筛选下拉选项
- 页面内提供占位符用法说明

---

# 十三、部署与配置

## 13.1 前端 — Vercel

1. Root Directory: `frontend`
2. Build Command: `npm run build`
3. 环境变量：`VITE_API_BASE_URL`

## 13.2 后端 — Railway / VPS

1. Root Directory: `backend`
2. Build: `pip install -r requirements.txt`
3. Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. 如需兼容旧的本地上传文件，可挂载目录：
  - `/app/uploads`

## 13.3 环境变量


| 配置项                           | 默认值                              | 说明                        |
| ----------------------------- | -------------------------------- | ------------------------- |
| `SECRET_KEY`                  | `change-me-in-production`        | JWT 签名密钥                  |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440`                           | Token 有效期（分钟）             |
| `DATABASE_URL`                | 空                                  | 完整 MySQL 连接串，优先级高于 `DB_*` |
| `DB_HOST`                     | `sh-cynosdbmysql-grp-kmfw4ojg.sql.tencentcdb.com` | 开发环境 MySQL 主机 |
| `DB_PORT`                     | `20396`                            | 开发环境 MySQL 端口             |
| `DB_USER`                     | 无默认值                             | MySQL 用户名                  |
| `DB_PASSWORD`                 | 无默认值                             | MySQL 密码                   |
| `DB_NAME`                     | 无默认值                             | MySQL 数据库名                 |
| `DB_CHARSET`                  | `utf8mb4`                          | MySQL 连接字符集               |
| `UPLOAD_DIR`                  | `backend/uploads`                | 上传文件与生成结果存储路径             |
| `AI_API_URL`                  | `https://nanoapi.poloai.top/...` | 默认生图接口迁移种子地址              |
| `AI_TIMEOUT`                  | `120`                            | AI 接口超时时间                 |
| `COS_STS_DURATION_SECONDS`    | `1800`                           | 腾讯云 COS 临时凭证有效期（秒）        |
| `IMAGE_FETCH_TIMEOUT`         | `30`                             | 后端读取远程参考图 / 原图 / 蒙版时的超时时间 |
| `REDIS_URL`                   | `redis://localhost:6379/0`       | Redis 地址（可选）              |


> Gemini Key、Tongyi Key、腾讯云 COS 密钥与桶配置、联系二维码、外部接口配置、场景绑定均通过后台写入数据库，不存放在前端配置中。

---

# 十四、关键设计原则

1. **默认首页模版化**：先看创意模版，再进入自定义创作
2. **三种创作入口统一到一个页面**：文生图、局部重绘、提示词反推统一在 `/generate`
3. **动作级登录校验**：浏览开放，上传 / 生成 / 历史 / 反推等动作强制登录
4. **积分驱动能力使用**：图片生成与提示词反推均走统一积分系统，且按场景动态配置扣费
5. **配置动态化**：Gemini、Tongyi、联系二维码在后台配置后即时生效
6. **生成结果可回流编辑**：历史记录与创意模版都可回填到生成页
7. **局部重绘前端可视化**：前端看到半透明蒙层，后端拿到纯黑白蒙版
8. **失败兜底统一**：生图失败显示统一错误图，接口异常给出明确提示
9. **接口与场景解耦**：接口配置只维护接口信息，调用场景通过独立绑定关系决定

