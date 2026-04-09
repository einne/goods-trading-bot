-- SmartSupport PostgreSQL schema
-- Designed for COMP7940 project: campus second-hand Telegram chatbot

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1) Users
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    telegram_user_id TEXT UNIQUE NOT NULL,
    display_name TEXT,
    username TEXT,
    role TEXT DEFAULT 'STUDENT',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2) Items (for query/publish/delist)
CREATE TABLE IF NOT EXISTS items (
    id BIGSERIAL PRIMARY KEY,
    seller_id BIGINT NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    condition_level TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DELISTED', 'SOLD')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3) Campus events
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    event_type TEXT NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ,
    location TEXT NOT NULL,
    details TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'CANCELLED', 'ARCHIVED')),
    created_by BIGINT REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4) FAQ knowledge base
CREATE TABLE IF NOT EXISTS faq (
    id BIGINT PRIMARY KEY,
    category TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    keywords TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5) Intent map
CREATE TABLE IF NOT EXISTS intents (
    id BIGINT PRIMARY KEY,
    intent TEXT NOT NULL UNIQUE,
    faq_id BIGINT REFERENCES faq(id),
    category TEXT NOT NULL,
    sample_utterance TEXT NOT NULL,
    keywords TEXT NOT NULL,
    route TEXT NOT NULL CHECK (route IN ('faq', 'escalate', 'human')),
    priority INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6) Escalation rules
CREATE TABLE IF NOT EXISTS escalation_rules (
    id BIGINT PRIMARY KEY,
    rule_name TEXT NOT NULL UNIQUE,
    trigger_faq_ids TEXT,
    trigger_intent TEXT NOT NULL,
    trigger_keywords TEXT NOT NULL,
    extra_condition TEXT,
    escalation_level TEXT NOT NULL CHECK (escalation_level IN ('L1', 'L2', 'L3')),
    target_queue TEXT NOT NULL,
    sla_minutes INTEGER NOT NULL CHECK (sla_minutes > 0),
    action TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7) Full-chain conversation logs (for observability/cost)
CREATE TABLE IF NOT EXISTS user_logs (
    id BIGSERIAL PRIMARY KEY,
    request_id UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES users(id),
    telegram_user_id TEXT,
    raw_input TEXT NOT NULL,
    detected_intent TEXT,
    route_mode TEXT,
    faq_id BIGINT REFERENCES faq(id),
    rule_id BIGINT REFERENCES escalation_rules(id),
    bot_response TEXT NOT NULL,
    llm_model TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    llm_estimated_cost NUMERIC(12, 6),
    latency_ms INTEGER,
    is_fallback BOOLEAN NOT NULL DEFAULT FALSE,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8) Item operation audit log
CREATE TABLE IF NOT EXISTS item_actions (
    id BIGSERIAL PRIMARY KEY,
    item_id BIGINT NOT NULL REFERENCES items(id),
    actor_user_id BIGINT REFERENCES users(id),
    action_type TEXT NOT NULL CHECK (action_type IN ('PUBLISH', 'EDIT', 'DELIST', 'RELIST', 'MARK_SOLD')),
    action_note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_items_status_created ON items(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_category_price ON items(category, price);
CREATE INDEX IF NOT EXISTS idx_events_starts_status ON events(starts_at, status);
CREATE INDEX IF NOT EXISTS idx_user_logs_created ON user_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_logs_intent ON user_logs(detected_intent);
CREATE INDEX IF NOT EXISTS idx_user_logs_telegram_user ON user_logs(telegram_user_id);

