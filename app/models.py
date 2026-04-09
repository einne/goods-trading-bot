"""Data models used by SmartSupport services."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class FAQItem:
    id: int
    category: str
    question: str
    answer: str
    keywords: str
    priority: int
    is_active: bool


@dataclass
class IntentItem:
    id: int
    intent: str
    faq_id: int
    category: str
    sample_utterance: str
    keywords: str
    route: str
    priority: int
    is_active: bool


@dataclass
class Item:
    id: int
    seller_id: int
    title: str
    category: str
    price: float
    condition_level: str
    description: str
    status: str
    created_at: Optional[datetime] = None


@dataclass
class Event:
    id: int
    title: str
    event_type: str
    starts_at: datetime
    ends_at: Optional[datetime]
    location: str
    details: str
    status: str


@dataclass
class UserLog:
    id: int
    telegram_user_id: str
    raw_input: str
    detected_intent: Optional[str]
    route_mode: Optional[str]
    bot_response: str
    llm_model: Optional[str]
    latency_ms: Optional[int]
    created_at: Optional[datetime] = None
