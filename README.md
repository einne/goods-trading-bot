# SmartSupport Bot 

校园二手平台 Telegram Chatbot，按课程方案实现云原生分层架构：

- Telegram 接入层
- 核心逻辑层（意图识别 / FAQ / 升级 / 物品 / 活动）
- 云数据层（PostgreSQL）
- DevOps 层（Docker + Compose + GitHub Actions）
- 可观测层（user_logs 全链路日志）

## Project Structure

- `app/`
- `app/chatbot.py`: Telegram 主流程入口
- `app/ChatGPT_HKBU.py`: LLM 客户端
- `app/db.py`: 数据库连接与日志写入（PostgreSQL + SQLite fallback）
- `app/models.py`: 数据实体模型
- `app/services/`: FAQ / Intent / Escalation / Item / Event 服务
- `data/`: FAQ/Intent/升级规则 + 物品/活动种子数据
- `database/schema_postgres.sql`: PostgreSQL 建表脚本
- `docs/database_design.md`: 数据库设计说明
- `.github/workflows/deploy.yml`: CI 基础流程

## Database

课程方案对应核心表：

- `users`
- `items`
- `events`
- `faq`
- `intents`
- `escalation_rules`
- `user_logs`
- `item_actions`

本地 Docker 启动 PostgreSQL 时会自动执行：

- `database/schema_postgres.sql`

## Local Run (Beginner)

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 填配置（任选其一）

- 在 `config.ini` 填 `TELEGRAM ACCESS_TOKEN` 与 `CHATGPT API_KEY`
- 或使用环境变量（推荐云部署）：
  - `TELEGRAM_ACCESS_TOKEN`
  - `CHATGPT_API_KEY`
  - `DATABASE_URL`

3. 启动 Bot

```bash
python app/chatbot.py
```

4. （可选）初始化种子数据到数据库

```bash
python scripts/seed_data.py
```

## Docker Run

1. 复制环境变量模板

```bash
cp .env.example .env
```

2. 编辑 `.env`（至少填 Token / API Key）

3. 启动

```bash
docker compose up --build -d
```

## Runtime Flow

1. 用户在 Telegram 发消息
2. `intent_seed.csv` 匹配意图
3. 按 `route` 走 FAQ 或升级规则
4. 未命中时回退 LLM
5. 所有交互写入 `user_logs`

## Telegram Commands

- `/start` 或 `/help`: 查看命令说明
- `/items [keyword]`: 查询在售物品
- `/publish title|category|price|condition|description`: 发布物品
- `/delist <item_id>`: 下架自己发布的物品
- `/events [keyword]`: 查询校园二手活动

## Seed Data

- `data/items_seed.csv`: 20 条校园二手物品示例数据
- `data/events_seed.csv`: 校园活动示例数据
- 初始化命令：`python scripts/seed_data.py`
