# 异步生图任务

## 接口说明

异步模式适合以下场景：

- 调用方不希望长时间占用单个 HTTP 连接。
- 需要自己控制轮询节奏、重试策略或超时策略。
- 需要批量提交多个任务后统一查询状态。

异步调用分为两步：

1. 调用 `POST /api/tasks/submit` 提交任务，拿到 `task_id`
2. 调用 `GET /api/tasks/{task_id}` 或 `GET /api/tasks?task_ids=...` 轮询结果

## 第一步：提交任务

### 请求信息

| 项目 | 内容 |
| --- | --- |
| URL | `/api/tasks/submit` |
| Method | `POST` |
| Content-Type | `application/json` |
| 鉴权 | 需要 API Key |

### Header

| 参数名 | 必填 | 示例 | 说明 |
| --- | --- | --- | --- |
| `X-API-Key` | 是 | `sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` | 用户 API Key。 |

### Body 参数

`POST /api/tasks/submit` 的 Body 与同步接口 `POST /api/tasks` 完全一致，可直接复用同一套请求结构：

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `mode` | string | 否 | `generate` | 任务模式。当前仅支持 `generate`。 |
| `model` | string | 是 | - | 场景标识，<strong>必填</strong>。须根据是否传入 `reference_images` 选择对应取值：<br><br><strong>文生图</strong>（未传 `reference_images` 或传空数组）：<table><thead><tr><th>model</th><th>对应官网模型</th></tr></thead><tbody><tr><td>`gptimage25_flare_high`</td><td>⚡️ Image 2.5 Flare</td></tr><tr><td>`gptimage25_sunburst_high`</td><td>⚡️ Image 2.5 Sunburst</td></tr><tr><td>`gptimage2_high`</td><td>⚡️ Image 2 (顶级)</td></tr><tr><td>`gptimage2_medium`</td><td>⚡️ Image 2 (高质量)</td></tr><tr><td>`gptimage2_low`</td><td>⚡️ Image 2 (性价比)</td></tr><tr><td>`banana_pro`</td><td>🍌 Nano Banana Pro</td></tr><tr><td>`banana2`</td><td>🍌 Nano Banana 2</td></tr><tr><td>`banana2_lite`</td><td>🍌 Nano Banana 2 Lite</td></tr><tr><td>`banana`</td><td>🍌 Nano Banana</td></tr></tbody></table><br><strong>图编辑</strong>（传入 `reference_images`）：<table><thead><tr><th>model</th><th>对应官网模型</th></tr></thead><tbody><tr><td>`gptimage25_flare_high_edit`</td><td>⚡️ Image 2.5 Flare</td></tr><tr><td>`gptimage25_sunburst_high_edit`</td><td>⚡️ Image 2.5 Sunburst</td></tr><tr><td>`gptimage2_high_edit`</td><td>⚡️ Image 2 (顶级)</td></tr><tr><td>`gptimage2_medium_edit`</td><td>⚡️ Image 2 (高质量)</td></tr><tr><td>`gptimage2_low_edit`</td><td>⚡️ Image 2 (性价比)</td></tr><tr><td>`banana_pro_edit`</td><td>🍌 Nano Banana Pro</td></tr><tr><td>`banana2_edit`</td><td>🍌 Nano Banana 2</td></tr><tr><td>`banana2_edit_lite`</td><td>🍌 Nano Banana 2 Lite</td></tr><tr><td>`banana_edit`</td><td>🍌 Nano Banana</td></tr></tbody></table> |
| `prompt` | string | 是 | - | 提示词，不能为空，最长 5000 字符。 |
| `size` | string | 否 | `3:4` | 图片宽高比，例如 `1:1`、`3:4`、`9:16`。可选值见 `GET /api/config/task-scenes` 的 `aspect_ratio_options`。 |
| `resolution` | string | 否 | `4K` | 清晰度档位，例如 `1K`、`2K`、`4K`。可选值见 `GET /api/config/task-scenes` 的 `image_size_options`。 |
| `reference_images` | string[] | 否 | `null` | 参考图数组，元素为 base64 字符串或 `data:image/...;base64,...` 形式。图编辑时必填。 |

### 提交示例

```bash
curl --request POST \
  --url "https://api.80ai.net/api/tasks/submit" \
  --header "Content-Type: application/json" \
  --header "X-API-Key: sk-yourApiKey" \
  --data '{
    "mode": "generate",
    "model": "banana_pro",
    "prompt": "一只穿宇航服的橘猫，站在月球表面，电影感光影，超清细节",
    "size": "1:1",
    "resolution": "2K"
  }'
```

### 图编辑提交示例

```bash
curl --request POST \
  --url "https://api.80ai.net/api/tasks/submit" \
  --header "Content-Type: application/json" \
  --header "X-API-Key: sk-yourApiKey" \
  --data '{
    "mode": "generate",
    "model": "banana2_edit",
    "prompt": "保持人物姿势不变，把背景换成海边日落",
    "size": "3:4",
    "resolution": "2K",
    "reference_images": [
      "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA..."
    ]
  }'
```

### 提交成功响应

```json
{
  "task_id": "biz_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "task_ids": [
    "biz_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  ]
}
```

### 提交响应字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_id` | string \| null | 首个任务 ID。当前 API 每次默认只创建 1 个任务，通常与 `task_ids[0]` 相同。 |
| `task_ids` | string[] | 本次提交产生的任务 ID 列表。 |

## 第二步：查询单个任务

### 请求信息

| 项目 | 内容 |
| --- | --- |
| URL | `/api/tasks/{task_id}` |
| Method | `GET` |
| 鉴权 | 需要 API Key |

### 查询示例

```bash
curl --request GET \
  --url "https://api.80ai.net/api/tasks/biz_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
  --header "X-API-Key: sk-yourApiKey"
```

### 任务进行中响应示例

```json
{
  "id": "biz_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "mode": "generate",
  "model": "banana_pro",
  "prompt": "一只穿宇航服的橘猫，站在月球表面，电影感光影，超清细节",
  "size": "1:1",
  "resolution": "2K",
  "credit_cost": 10,
  "credit_refunded": false,
  "status": "processing",
  "error_message": "",
  "created_at": "2026-05-27T14:30:00",
  "enqueued_at": "2026-05-27T14:30:00",
  "request_started_at": null,
  "request_finished_at": null,
  "images": [
    {
      "id": 123,
      "image_url": "",
      "preview_url": "",
      "thumb_url": "",
      "status": "pending",
      "error_message": "",
      "image_format": "",
      "image_size_bytes": 0
    }
  ]
}
```

### 任务完成响应示例

```json
{
  "id": "biz_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "mode": "generate",
  "model": "banana_pro",
  "prompt": "一只穿宇航服的橘猫，站在月球表面，电影感光影，超清细节",
  "size": "1:1",
  "resolution": "2K",
  "credit_cost": 10,
  "credit_refunded": false,
  "status": "success",
  "error_message": "",
  "created_at": "2026-05-27T14:30:00",
  "enqueued_at": "2026-05-27T14:30:00",
  "request_started_at": "2026-05-27T14:30:02",
  "request_finished_at": "2026-05-27T14:30:18",
  "images": [
    {
      "id": 123,
      "image_url": "https://cdn.example.com/generated/xxx.png",
      "preview_url": "",
      "thumb_url": "https://cdn.example.com/generated/xxx.png",
      "status": "success",
      "error_message": "",
      "image_format": "png",
      "image_size_bytes": 2048000
    }
  ]
}
```

## 第三步：批量查询多个任务

### 请求信息

| 项目 | 内容 |
| --- | --- |
| URL | `/api/tasks?task_ids=taskA&task_ids=taskB` |
| Method | `GET` |
| 鉴权 | 需要 API Key |

### 查询示例

```bash
curl --request GET \
  --url "https://api.80ai.net/api/tasks?task_ids=biz_taskA&task_ids=biz_taskB" \
  --header "X-API-Key: sk-yourApiKey"
```

批量查询返回 `TaskOut[]`，单个元素结构与同步接口 `POST /api/tasks` 成功响应中的任务对象一致。

## 异步状态说明

| 状态 | 说明 |
| --- | --- |
| `pending` | 任务已创建，等待进入队列。 |
| `queued` | 任务已入队，等待 worker 处理。 |
| `processing` | worker 正在处理任务。 |
| `success` | 任务处理成功，可读取 `images[].image_url`。 |
| `failed` | 任务处理失败，可查看 `error_message` 和 `images[].error_message`。 |

建议轮询间隔为 2 到 5 秒；当任务进入 `success` 或 `failed` 后即可停止轮询。

## 错误示例

```json
{
  "detail": "积分不足，需要 10 积分，当前余额 5"
}
```

```json
{
  "detail": "model 不能为空"
}
```

```json
{
  "detail": "图编辑须传入 reference_images"
}
```

```json
{
  "detail": "reference_images[0] 必须是图片 base64"
}
```

```json
{
  "detail": "任务队列暂不可用，请稍后重试"
}
```

## 注意事项

- `POST /api/tasks/submit` 默认创建 1 个任务，返回的 `task_id` 可用于后续查询。
- 图编辑与文生图共用同一组 Body 参数；须根据是否传入 `reference_images` 选择对应的 `model` 取值。
- 异步模式下，图编辑请求中的 `reference_images` 可以继续直接传 base64 或 data URL；服务端会自动转为可供 worker 读取的持久化引用。
- `size`、`resolution` 是否生效取决于所选 `model`，可先调用 `GET /api/config/task-scenes` 查看场景配置。
