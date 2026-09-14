# 80AI API 生图接口文档

## 基础信息

- Base URL：`https://api.80ai.net`
- 数据格式：请求与响应均为 JSON。
- 鉴权方式：需要鉴权的接口支持以下任一 Header：

```http
X-API-Key: sk-yourApiKey
```

或：

```http
Authorization: Bearer sk-yourApiKey
```

## 通用错误响应

```json
{
  "detail": "错误说明"
}
```

常见状态码：

- `400`：请求参数错误、积分不足、业务校验失败。
- `401`：缺少 API Key 或 API Key 无效。
- `403`：API Key 禁用/过期、账号禁用、无权访问资源。
- `502`：AI 服务调用失败或同步处理失败。

## 推荐调用流程

1. 查询可用模型/场景配置：`GET /api/config/generation-models`、`GET /api/config/task-scenes`。
2. 如需参考图，将图片转为 base64 或 data URL，直接放入创建任务参数。
3. 二选一发起任务：
   - 同步调用：`POST /api/tasks`，接口会等待处理完成并直接返回结果。
   - 异步调用：`POST /api/tasks/submit` 获取 `task_id`，再通过 `GET /api/tasks/{task_id}` 或 `GET /api/tasks?task_ids=...` 查询结果。

## 文档列表

- [查询生图模型列表](./01-get-generation-models.md)
- [查询任务场景配置](./02-get-task-scenes.md)
- [创建同步生图任务](./03-create-task.md)
- [异步生图任务](./04-async-task.md)

## 更新静态站点

文档源文件为 `docs-api/*.md`，浏览器实际访问的是 `docs-api/docs-api/` 下的 HTML。**修改 `.md` 后必须执行构建**，否则 HTML 不会变：

```bash
cd docs-api
python3 build_site.py
```

构建完成后，本地预览请硬刷新浏览器（Cmd+Shift+R）。线上 https://80ai.net/docs-api/ 需重新部署 `docs-api/docs-api/` 目录。

> 注意：请直接编辑 `*.md` 源文件，不要手改 `docs-api/docs-api/` 下的 HTML。运行 `build_site.py` 会覆盖 HTML，手改内容会丢失。
