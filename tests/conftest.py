"""pytest 公共夹具：真实 PostgreSQL 16 + 真实 alembic 迁移。

不 mock 数据库 —— 验收标准第 1、4 条（迁移往返、唯一约束）必须在真库上验。
连接串从 ``DATABASE_URL`` 读；库不存在时整组用例 skip 而不是 error。
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

URL = os.environ.get("DATABASE_URL", "").strip()


def _alembic(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(ROOT),
        env={**os.environ, "DATABASE_URL": URL},
        capture_output=True,
        text=True,
        timeout=180,
    )


@pytest.fixture(scope="session")
def alembic_cli():
    return _alembic


@pytest.fixture(scope="session")
def engine():
    from sqlalchemy import create_engine

    if not URL:
        pytest.skip("未设置 DATABASE_URL")
    eng = create_engine(URL, future=True)
    try:
        with eng.connect() as c:
            c.exec_driver_sql("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DATABASE_URL 连不上：{exc}")
    yield eng
    eng.dispose()


@pytest.fixture(scope="session")
def migrated(engine):
    """把库迁到最新版本；用例跑完回滚到 base，保证可重复执行。"""
    r = _alembic("upgrade", "head")
    assert r.returncode == 0, f"alembic upgrade 失败：{r.stderr}"
    yield
    _alembic("downgrade", "base")


@pytest.fixture()
def db(engine, migrated):
    """每个用例前清空两表，用例拿到一个 Session。"""
    from sqlalchemy.orm import Session

    with engine.begin() as c:
        c.exec_driver_sql("TRUNCATE survey_responses, event_surveys CASCADE")
    with Session(engine) as session:
        yield session
        session.rollback()


# --------------------------------------------------------------- 造数辅助

ORG = uuid.UUID("11111111-1111-4111-8111-111111111111")
SITE = uuid.UUID("22222222-2222-4222-8222-222222222222")
USER = uuid.UUID("33333333-3333-4333-8333-333333333333")

VALID_QUESTIONS = [
    {"id": "q1", "type": "rating", "title": "整体满意度", "required": True, "scale": "star5"},
    {"id": "q2", "type": "single", "title": "参与方式", "required": True,
     "options": [{"id": "o1", "label": "现场"}, {"id": "o2", "label": "线上"}]},
    {"id": "q3", "type": "multi", "title": "帮助较大的环节", "required": False,
     "min_select": 1, "max_select": 2,
     "options": [{"id": "o1", "label": "分享"}, {"id": "o2", "label": "洽谈"},
                 {"id": "o3", "label": "参观"}]},
    {"id": "q4", "type": "text", "title": "建议", "required": False, "max_length": 200},
]


def make_survey(db, *, event_id: uuid.UUID | None = None, org_id: uuid.UUID = ORG,
                status: str = "published", questions=None, open_days: int = -1,
                close_days: int = 6):
    """插一份问卷并 flush（拿到 id），返回 ORM 对象。"""
    from app.models import EventSurvey

    now = datetime.now(timezone.utc)
    row = EventSurvey(
        org_id=org_id, site_id=SITE, created_by=USER,
        event_id=event_id or uuid.uuid4(),
        title="示例问卷", intro="虚构数据", questions=questions or VALID_QUESTIONS,
        open_at=now + timedelta(days=open_days), close_at=now + timedelta(days=close_days),
        status=status, anonymous=False,
    )
    db.add(row)
    db.flush()
    return row


def make_response(db, survey, *, member_id: uuid.UUID | None = None, answers=None):
    from app.models import SurveyResponse

    row = SurveyResponse(
        org_id=survey.org_id, site_id=survey.site_id, created_by=USER,
        survey_id=survey.id, event_id=survey.event_id,
        member_id=member_id or uuid.uuid4(),
        answers=answers or {"q1": 4, "q2": "o1"},
        client_version="1.0.0",
    )
    db.add(row)
    db.flush()
    return row
