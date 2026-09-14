# 创建同步生图任务

## 接口说明

创建文生图或图编辑任务。接口会等待生图处理完成，直接返回最终任务结果。局部重绘和提示词反推暂不开放 API。

### 请求信息

| 项目 | 内容 |
| --- | --- |
| URL | `/api/tasks` |
| Method | `POST` |
| Content-Type | `application/json` |
| 鉴权 | 需要 API Key |

### Header

| 参数名 | 必填 | 示例 | 说明 |
| --- | --- | --- | --- |
| `X-API-Key` | 是 | `sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` | 用户 API Key。 |

### Body 参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `mode` | string | 否 | `generate` | 任务模式。当前仅支持 `generate`。 |
| `model` | string | 是 | - | 场景标识，<strong>必填</strong>。须根据是否传入 `reference_images` 选择对应取值：<br><br><strong>文生图</strong>（未传 `reference_images` 或传空数组）：<table><thead><tr><th>model</th><th>对应官网模型</th></tr></thead><tbody><tr><td>`gptimage25_flare_high`</td><td>⚡️ Image 2.5 Flare</td></tr><tr><td>`gptimage25_sunburst_high`</td><td>⚡️ Image 2.5 Sunburst</td></tr><tr><td>`gptimage2_high`</td><td>⚡️ Image 2 (顶级)</td></tr><tr><td>`gptimage2_medium`</td><td>⚡️ Image 2 (高质量)</td></tr><tr><td>`gptimage2_low`</td><td>⚡️ Image 2 (性价比)</td></tr><tr><td>`banana_pro`</td><td>🍌 Nano Banana Pro</td></tr><tr><td>`banana2`</td><td>🍌 Nano Banana 2</td></tr><tr><td>`banana2_lite`</td><td>🍌 Nano Banana 2 Lite</td></tr><tr><td>`banana`</td><td>🍌 Nano Banana</td></tr></tbody></table><br><strong>图编辑</strong>（传入 `reference_images`）：<table><thead><tr><th>model</th><th>对应官网模型</th></tr></thead><tbody><tr><td>`gptimage25_flare_high_edit`</td><td>⚡️ Image 2.5 Flare</td></tr><tr><td>`gptimage25_sunburst_high_edit`</td><td>⚡️ Image 2.5 Sunburst</td></tr><tr><td>`gptimage2_high_edit`</td><td>⚡️ Image 2 (顶级)</td></tr><tr><td>`gptimage2_medium_edit`</td><td>⚡️ Image 2 (高质量)</td></tr><tr><td>`gptimage2_low_edit`</td><td>⚡️ Image 2 (性价比)</td></tr><tr><td>`banana_pro_edit`</td><td>🍌 Nano Banana Pro</td></tr><tr><td>`banana2_edit`</td><td>🍌 Nano Banana 2</td></tr><tr><td>`banana2_edit_lite`</td><td>🍌 Nano Banana 2 Lite</td></tr><tr><td>`banana_edit`</td><td>🍌 Nano Banana</td></tr></tbody></table> |
| `prompt` | string | 是 | - | 提示词，不能为空，最长 5000 字符。 |
| `size` | string | 否 | `3:4` | 图片宽高比，例如 `1:1`、`3:4`、`9:16`。可选值见 `GET /api/config/task-scenes` 的 `aspect_ratio_options`。 |
| `resolution` | string | 否 | `4K` | 清晰度档位，例如 `1K`、`2K`、`4K`。可选值见 `GET /api/config/task-scenes` 的 `image_size_options`。 |
| `reference_images` | string[] | 否 | `null` | 参考图数组，元素为 base64 字符串或 `data:image/...;base64,...` 形式。<strong>图编辑时必填</strong>（至少 1 张）。 |

### 文生图请求示例

```bash
curl --request POST \
  --url "https://api.80ai.net/api/tasks" \
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

### 图编辑请求示例

```bash
curl --request POST \
  --url "https://api.80ai.net/api/tasks" \
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

### 成功响应

```json
[
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
    "enqueued_at": null,
    "request_started_at": "2026-05-27T14:30:01",
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
]
```

### 响应字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `[].id` | string | 任务 ID。 |
| `[].status` | string | 处理结果：`success` 或 `failed`。 |
| `[].credit_cost` | number | 本任务消耗积分。 |
| `[].credit_refunded` | boolean | 失败时是否已退款。 |
| `[].images[].id` | number | 图片 ID。 |
| `[].images[].image_url` | string | 生成图片 URL。 |
| `[].images[].status` | string | 图片状态。 |
| `[].images[].error_message` | string | 图片错误信息。 |
| `[].error_message` | string | 任务级错误信息。 |

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
  "detail": "文生图 model 无效，可选值：banana、banana2、banana_pro、gptimage25_flare_high、gptimage25_sunburst_high、gptimage2_high、gptimage2_low、gptimage2_medium"
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
  "detail": "任务同步处理失败：生图接口请求超时（600 秒）"
}
```

## 注意事项

- 图编辑与文生图共用同一组 Body 参数；须根据是否传入 `reference_images` 选择对应的 `model` 取值。
- `size`、`resolution` 是否生效取决于所选 `model`，可先调用 `GET /api/config/task-scenes` 查看场景配置。
- 每个 `POST /api/tasks` 请求默认生成 1 张图片，并按场景单价扣积分。
- 接口会等待外部 AI 服务返回，调用方需要设置足够长的 HTTP 超时时间。
- 如果生成失败，响应仍可能返回任务对象，`status` 为 `failed`，并带有 `error_message`。
