"""验收标准第 1 条：迁移 upgrade / downgrade 均成功，alembic check 无漂移。

真库用例（PostgreSQL 16），需要 ``DATABASE_URL``。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

UNIFIED = {"id", "org_id", "site_id", "created_at", "created_by", "updated_at", "deleted_at"}

SURVEY_COLUMNS = UNIFIED | {
    "event_id", "title", "intro", "questions", "open_at", "close_at", "status", "anonymous",
}
RESPONSE_COLUMNS = UNIFIED | {
    "survey_id", "event_id", "member_id", "signup_id", "answers", "submitted_at",
    "client_version",
}


def columns(conn, table: str) -> set[str]:
    rows = conn.exec_driver_sql(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s",
        (table,),
    ).fetchall()
    return {r[0] for r in rows}


# ------------------------------------------------------------------ 迁移往返

def test_迁移可回滚再升级(alembic_cli, engine):
    """downgrade base → upgrade head → downgrade base → upgrade head，全程无异常。"""
    try:
        r = alembic_cli("downgrade", "base")
        assert r.returncode == 0, r.stderr
        with engine.connect() as c:
            assert columns(c, "event_surveys") == set(), "downgrade 后表应已删除"
            assert columns(c, "survey_responses") == set()

        r = alembic_cli("upgrade", "head")
        assert r.returncode == 0, r.stderr
        with engine.connect() as c:
            assert columns(c, "event_surveys") == SURVEY_COLUMNS
            assert columns(c, "survey_responses") == RESPONSE_COLUMNS
    finally:
        assert alembic_cli("upgrade", "head").returncode == 0


def test_alembic_check_无漂移(alembic_cli):
    """ORM metadata 与迁移建出来的结构必须一致（compare_type=True）。"""
    r = alembic_cli("check")
    assert r.returncode == 0, f"检测到漂移：\n{r.stdout}\n{r.stderr}"
    assert re.search(r"No new upgrade operations", r.stdout + r.stderr), r.stdout


def test_current_版本号(alembic_cli):
    r = alembic_cli("current")
    assert r.returncode == 0
    assert "20261125_01" in (r.stdout + r.stderr)


# ------------------------------------------------------------------ 结构与约束

def test_两张表都存在(engine):
    with engine.connect() as c:
        rows = c.exec_driver_sql(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name IN "
            "('event_surveys','survey_responses') ORDER BY table_name"
        ).fetchall()
    assert [r[0] for r in rows] == ["event_surveys", "survey_responses"]


def test_统一七字段齐全(engine):
    with engine.connect() as c:
        for table in ("event_surveys", "survey_responses"):
            assert UNIFIED <= columns(c, table), f"{table} 缺少统一字段"


def test_字段类型符合约定(engine):
    with engine.connect() as c:
        rows = c.exec_driver_sql(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name IN "
            "('event_surveys','survey_responses')"
        ).fetchall()
    types = {(t, col): dt for t, col, dt in rows}
    assert types[("event_surveys", "questions")] == "jsonb"
    assert types[("survey_responses", "answers")] == "jsonb"
    assert types[("event_surveys", "id")] == "uuid"
    assert types[("survey_responses", "submitted_at")].startswith("timestamp")
    assert types[("event_surveys", "anonymous")] == "boolean"


def test_唯一索引与唯一约束存在(engine):
    with engine.connect() as c:
        idx = {r[0] for r in c.exec_driver_sql(
            "SELECT indexname FROM pg_indexes WHERE schemaname = current_schema()"
        ).fetchall()}
        cons = {r[0] for r in c.exec_driver_sql(
            "SELECT conname FROM pg_constraint WHERE connamespace = current_schema()::regnamespace"
        ).fetchall()}
    assert "uq_event_surveys_org_event" in idx
    assert "uq_survey_responses_survey_member" in cons


def test_软删除用部分唯一索引(engine):
    """event_id 的唯一性只在未软删时生效，删掉后可以重建同一活动的问卷。"""
    with engine.connect() as c:
        ddl = c.exec_driver_sql(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_event_surveys_org_event'"
        ).scalar()
    assert "UNIQUE" in ddl.upper()
    assert "deleted_at IS NULL" in ddl


# ------------------------------------------------------------------ DDL 单一来源

def test_迁移读取schema目录而不是内联SQL():
    """把 DDL 放在 schema/*.sql 里，迁移只负责读取 —— 防止三处漂移。"""
    mig = (ROOT / "alembic" / "versions" / "20261125_01_event_surveys.py").read_text(encoding="utf-8")
    assert "_SCHEMA" in mig and "read_text" in mig
    assert "CREATE TABLE" not in mig.upper(), "迁移里不应内联 CREATE TABLE"
    for name in ("event_surveys.sql", "survey_responses.sql"):
        assert (ROOT / "schema" / name).exists()
