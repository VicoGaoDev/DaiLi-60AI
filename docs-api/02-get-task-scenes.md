# 查询任务场景配置

## 接口说明

获取当前 API 开放的任务场景配置，仅包含文生图和图编辑场景。调用方可根据 `scene_type` 判断场景用途，并读取积分单价、参考图数量和尺寸选项。

## 请求信息

| 项目 | 内容 |
| --- | --- |
| URL | `/api/config/task-scenes` |
| Method | `GET` |
| Content-Type | 无 |
| 鉴权 | 不需要 |

## 请求参数

无。

## 请求示例

```bash
curl --request GET \
  --url "https://api.80ai.net/api/config/task-scenes"
```

## 成功响应

```json
[
  {
    "scene_key": "banana_pro",
    "scene_type": "generate",
    "scene_label": "文生图",
    "scene_description": "根据文本提示词生成图片",
    "display_name": "Banana Pro",
    "subtitle": "高质量文生图",
    "sort_order": 10,
    "hide_aspect_ratio": false,
    "hide_resolution": false,
    "hide_custom_size": true,
    "credit_cost": 10,
    "max_reference_images": 3,
    "aspect_ratio_options": [
      { "label": "1:1", "value": "1:1" }
    ],
    "image_size_options": [
      { "label": "1K", "value": "1K" }
    ],
    "custom_size_options": [],
    "category_id": 1,
    "category_name": "Banana 系列",
    "category_sort_order": 10
  }
]
```

## 响应字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `scene_key` | string | 场景标识。文生图/图编辑通常作为 `model` 使用。 |
| `scene_type` | string | 场景类型：`generate`、`image_edit`。 |
| `scene_label` | string | 场景名称。 |
| `scene_description` | string | 场景说明。 |
| `credit_cost` | number | 单次/单张消耗积分。 |
| `max_reference_images` | number | 支持的参考图数量上限。 |
| `aspect_ratio_options` | array | 可选比例，对应创建任务时的 `size`。 |
| `image_size_options` | array | 可选清晰度，对应创建任务时的 `resolution`。 |
| `custom_size_options` | array | 可选自定义尺寸。 |
| `category_id` | number \| null | 所属生图场景分类 ID；未分类时为 `null`。 |
| `category_name` | string \| null | 所属分类名称；未分类时为 `null`。 |
| `category_sort_order` | number \| null | 所属分类排序；未分类时为 `null`。 |

## 注意事项

- 创建任务时使用 `size`、`resolution` 即可；部分场景会在服务端内部完成尺寸换算，无需额外传参。
- 局部重绘和提示词反推暂不开放 API，因此不会出现在本接口响应中。
