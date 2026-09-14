# 数据库迁移约定

从 `2026-06-18` 起，生产环境数据库变更不再依赖应用启动阶段的自动 schema 修复，统一改为手工执行版本化 SQL。

## 目录约定

- 文件命名：`YYYY-MM-DD-NNN__<short-description>.sql`
- 同一天内有多次变更时，按 `001`、`002`、`003` 递增
- 一个文件只承载一次可独立发布的数据库变更

## 执行顺序

1. 按文件名升序执行尚未执行过的 SQL。
2. SQL 执行完成后，再部署 `backend/` 与 `backend-api/`。
3. 生产环境保持：
   - `DB_RUN_STARTUP_SCHEMA_SYNC=false`
   - `DB_RUN_SCHEMA_COMPAT=false`

## 编写要求

- 优先写可重复执行或至少容易人工确认的 SQL。
- 需要数据回填时，把结构变更和数据修复写在同一个版本脚本里。
- 涉及高风险语句时，在文件顶部写清楚影响范围、回滚思路和执行前置条件。
- 应用代码依赖的新字段、新索引、新表，必须先提交对应 SQL，再发布代码。

## 基线说明

- `2026-06-18-001__manual-schema-migration-baseline.sql` 作为切换到手工迁移流程的基线记录。
- 无限画布相关迁移按以下顺序执行：
  - `2026-06-26-001__add-user-canvas.sql`：新增 `user_canvas`、`canvas_nodes`，并为 `tasks` 增加 `canvas_id`。
  - `2026-06-29-001__add-canvas-project-id.sql`：为画布增加 16 位公开 `project_id`，用于 `/canvas/:projectId` 路由。
  - `2026-06-29-002__add-canvas-free-nodes.sql`：支持自由文本节点和上传图片节点，使 `canvas_nodes.task_id` 可为空并增加 `node_type`、`content`、`image_url`。
- `2026-06-29-003__production-canvas-rollup.sql` 是生产上线便捷汇总脚本，包含以上三份无限画布迁移的最终结构；如果生产尚未执行 001/002，可直接执行该汇总脚本。不要在同一环境中既执行 001/002 又重复执行 003。
- 若后续需要把更早历史的自动修复逻辑完全回填为迁移脚本，可继续在本目录补充更细化的历史脚本说明。
