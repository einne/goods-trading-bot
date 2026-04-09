# 数据库表结构设计（基于项目方案）

面向 `校园二手平台 Telegram Chatbot` 的 PostgreSQL 设计，覆盖课程方案中的 4 大核心数据域与可观测日志需求。

## 核心表

- `users`：Telegram 用户主数据（买家/卖家/管理员）
- `items`：二手物品在售信息（支持发布、查询、下架、售出）
- `events`：校园活动信息（时间、地点、状态）
- `faq`：FAQ 知识库
- `intents`：意图路由配置（FAQ / escalate / human）
- `escalation_rules`：升级规则与 SLA
- `user_logs`：全链路日志（输入、意图、路由、回复、耗时、成本）
- `item_actions`：物品操作审计日志

## 关系说明

- `items.seller_id -> users.id`
- `events.created_by -> users.id`
- `intents.faq_id -> faq.id`
- `user_logs.faq_id -> faq.id`
- `user_logs.rule_id -> escalation_rules.id`
- `item_actions.item_id -> items.id`
- `item_actions.actor_user_id -> users.id`

## 设计要点

- 使用 `TIMESTAMPTZ` 统一时区，方便云部署与日志分析。
- `status`/`route`/`escalation_level` 使用 `CHECK` 约束，避免脏数据。
- `user_logs` 记录 `latency_ms`、token、估算成本，支撑课程要求的可观测与成本控制。
- 通过索引优化 `items` 列表查询、`events` 时间检索、`user_logs` 监控报表查询。

## 建表脚本

- PostgreSQL 建表脚本：`database/schema_postgres.sql`

