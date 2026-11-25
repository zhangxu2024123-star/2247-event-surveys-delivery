"""SQLAlchemy 2 ORM 模型：``event_surveys`` / ``survey_responses``。

统一字段（7 个，见工单【统一技术约定】）由 :class:`BaseModel` 提供：
``id`` / ``org_id`` / ``site_id`` / ``created_at`` / ``created_by`` /
``updated_at`` / ``deleted_at``。

迁移（``alembic/versions/20261125_01_event_surveys.py``）以 ``schema/*.sql`` 为唯一
DDL 来源；本文件只负责 ORM 映射与业务侧读写，两者字段名/类型/约束保持一致。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SURVEY_STATUSES = ("draft", "published", "closed")


class Base(DeclarativeBase):
    pass


class BaseModel(Base):
    """7 个统一字段。业务表一律继承它。"""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EventSurvey(BaseModel):
    """一个活动一份问卷；``(org_id, event_id)`` 在未软删时唯一。"""

    __tablename__ = "event_surveys"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    intro: Mapped[str | None] = mapped_column(Text)
    questions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        comment="题目定义数组，最多 20 题，4 种题型 single/multi/rating/text",
    )
    open_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    close_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'draft'")
    )
    anonymous: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
        comment="统计时是否匿名：true 时展示层不返回 member_id",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','published','closed')", name="ck_event_surveys_status"
        ),
        CheckConstraint("close_at > open_at", name="ck_event_surveys_window"),
        CheckConstraint(
            "jsonb_typeof(questions) = 'array'", name="ck_event_surveys_questions_array"
        ),
        Index(
            "uq_event_surveys_org_event",
            "org_id",
            "event_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_event_surveys_status", "status"),
        {"comment": "会后问卷：一个活动一份，questions 为题型 JSON 数组（见 schema/questions.schema.json）"},
    )


class SurveyResponse(BaseModel):
    """一份答卷；同一会员对同一问卷只能有一份（唯一约束）。"""

    __tablename__ = "survey_responses"

    survey_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("event_surveys.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    member_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    signup_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    answers: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment='以题号为键的答案对象，如 {"q1": "o1", "q2": ["o1","o3"], "q3": 5}',
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    client_version: Mapped[str | None] = mapped_column(
        String(32), comment="小程序/工作台客户端版本号，便于排查提交异常"
    )

    __table_args__ = (
        UniqueConstraint("survey_id", "member_id", name="uq_survey_responses_survey_member"),
        CheckConstraint(
            "jsonb_typeof(answers) = 'object'", name="ck_survey_responses_answers_object"
        ),
        Index("ix_survey_responses_event_member", "event_id", "member_id"),
        {"comment": "会员答卷：同一会员对同一问卷仅一份（uq_survey_responses_survey_member）"},
    )
