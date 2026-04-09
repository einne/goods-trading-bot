# 原有项目框架调整说明（按作业方案）

## 调整目标

基于《HKBU COMP7940 云计算课程项目设计方案》，将原有 FAQ Bot 升级为支持以下 4 大业务域的可扩展框架：

- FAQ 智能问答
- 物品查询 / 发布 / 下架
- 校园活动查询
- 升级处理与人工转接

## 调整后的分层

1. 接入层  
`app/chatbot.py` 负责 Telegram 消息接入与响应。

2. 业务服务层  
`app/services/`
- `intent_service.py`：意图识别（基于 intent_seed）
- `faq_service.py`：FAQ 知识库读取
- `escalation_service.py`：升级规则读取
- `router_service.py`：FAQ / 升级 / LLM 回退路由
- `item_service.py`：物品数据查询接口
- `event_service.py`：活动数据查询接口

3. LLM 层  
`app/ChatGPT_HKBU.py`：LLM 请求与响应元数据（延迟、tokens）

4. 数据访问层  
`app/db.py`：数据库连接管理与 `user_logs` 结构化日志写入，支持：
- 云 PostgreSQL（`DATABASE_URL`）
- 本地 SQLite fallback（`data/smartsupport.db`）

5. 数据定义层  
- `database/schema_postgres.sql`：生产建表脚本
- `docs/database_design.md`：表结构说明

## 对课程要求的对应关系

- Telegram chatbot：`app/chatbot.py`
- LLM API：`app/ChatGPT_HKBU.py`
- 云数据库：PostgreSQL schema + `DATABASE_URL`
- 日志可观测：`user_logs` 表（意图、路由、耗时、成本字段）
- 容器化：`Dockerfile` + `docker-compose.yml`
- Git / CI：`.github/workflows/deploy.yml`

