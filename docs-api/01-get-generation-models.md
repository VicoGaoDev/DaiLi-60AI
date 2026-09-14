# 查询生图模型列表

## 接口说明

获取当前可用于普通生图任务的模型列表、展示文案、积分单价和可选尺寸配置。通常在创建任务前调用，用于决定 `POST /api/tasks` 的 `model`、`size`、`resolution`、`custom_size` 等参数。

## 请求信息

| 项目 | 内容 |
| --- | --- |
| URL | `/api/config/generation-models` |
| Method | `GET` |
| Content-Type | 无 |
| 鉴权 | 不需要 |

## 请求参数

无。

## 请求示例

```bash
curl --request GET \
  --url "https://api.80ai.net/api/config/generation-models"
```

## 成功响应

```json
[
  {
    "model_key": "banana_pro",
    "model_label": "Banana Pro",
    "model_description": "高质量通用生图模型",
    "display_name": "Banana Pro",
    "subtitle": "适合高质量创作",
    "sort_order": 10,
    "hide_aspect_ratio": false,
    "hide_resolution": false,
    "hide_custom_size": true,
    "custom_size_min": 256,
    "custom_size_max": 4096,
    "custom_size_step": 8,
    "credit_cost": 10,
    "max_reference_images": 3,
    "aspect_ratio_options": [
      { "label": "1:1", "value": "1:1" },
      { "label": "3:4", "value": "3:4" }
    ],
    "image_size_options": [
      { "label": "1K", "value": "1K" },
      { "label": "2K", "value": "2K" }
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
| `model_key` | string | 创建任务时传入的 `model`。 |
| `model_label` | string | 模型名称。 |
| `model_description` | string | 模型说明。 |
| `display_name` | string | 前端展示名称。 |
| `subtitle` | string | 前端副标题。 |
| `sort_order` | number | 排序值。 |
| `hide_aspect_ratio` | boolean | 是否隐藏比例参数。 |
| `hide_resolution` | boolean | 是否隐藏清晰度参数。 |
| `hide_custom_size` | boolean | 是否隐藏自定义尺寸参数；为 `false` 时主生图页可启用手动宽高。 |
| `custom_size_min` | number | 自定义宽高的最小值。 |
| `custom_size_max` | number | 自定义宽高的最大值。 |
| `custom_size_step` | number | 自定义宽高的递增步长。 |
| `credit_cost` | number | 单张图片消耗积分。 |
| `max_reference_images` | number | 最多参考图数量。 |
| `aspect_ratio_options` | array | 可选比例列表，对应任务参数 `size`。 |
| `image_size_options` | array | 可选清晰度列表，对应任务参数 `resolution`。 |
| `custom_size_options` | array | 可选自定义尺寸列表，对应任务参数 `custom_size`。 |
| `category_id` | number \| null | 所属生图场景分类 ID；未分类时为 `null`。 |
| `category_name` | string \| null | 所属分类名称；未分类时为 `null`。 |
| `category_sort_order` | number \| null | 所属分类排序；未分类时为 `null`。 |

## 注意事项

- 返回内容由后台“接口管理”配置决定。
- 如果 `model` 为空，创建任务时服务端会使用默认生图模型。
