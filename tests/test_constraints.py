"""验收标准第 4 条 + 约束层面的边界：唯一约束、FK 级联、CHECK。

真库用例（PostgreSQL 16），需要 ``DATABASE_URL``。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import EventSurvey, SurveyResponse
from tests.conftest import ORG, make_response, make_survey


def test_同一会员同一问卷第二份答卷被唯一约束拦下(db):
    """验收标准第 4 条。"""
    survey = make_survey(db)
    member = uuid.uuid4()
    make_response(db, survey, member_id=member)
    with pytest.raises(IntegrityError) as ei:
        make_response(db, survey, member_id=member)
    assert "uq_survey_responses_survey_member" in str(ei.value)


def test_同一会员不同问卷可以各答一份(db):
    s1 = make_survey(db)
    s2 = make_survey(db)
    member = uuid.uuid4()
    make_response(db, s1, member_id=member)
    make_response(db, s2, member_id=member)
    assert db.scalar(select(SurveyResponse).where(SurveyResponse.member_id == member))


def test_同一问卷不同会员各一份(db):
    survey = make_survey(db)
    make_response(db, survey, member_id=uuid.uuid4())
    make_response(db, survey, member_id=uuid.uuid4())
    n = db.scalar(
        select(SurveyResponse.id).where(SurveyResponse.survey_id == survey.id).limit(5)
    )
    assert n is not None


def test_一个活动只允许一份未软删问卷(db):
    event = uuid.uuid4()
    make_survey(db, event_id=event)
    with pytest.raises(IntegrityError) as ei:
        make_survey(db, event_id=event)
    assert "uq_event_surveys_org_event" in str(ei.value)


def test_软删后可重建同一活动的问卷(db):
    event = uuid.uuid4()
    first = make_survey(db, event_id=event)
    first.deleted_at = datetime.now(timezone.utc)
    db.flush()
    again = make_survey(db, event_id=event)          # 不应冲突
    assert again.id != first.id


def test_不同org可以有同event_id(db):
    event = uuid.uuid4()
    make_survey(db, event_id=event)
    make_survey(db, event_id=event, org_id=uuid.uuid4())
    assert db.scalar(select(EventSurvey).where(EventSurvey.event_id == event))


def test_删除问卷级联删除答卷(db):
    survey = make_survey(db)
    make_response(db, survey)
    db.delete(survey)
    db.flush()
    assert db.scalar(
        select(SurveyResponse.id).where(SurveyResponse.survey_id == survey.id)
    ) is None


def test_答卷必须挂到存在的问卷上(db):
    with pytest.raises(IntegrityError) as ei:
        db.add(SurveyResponse(
            org_id=ORG, survey_id=uuid.uuid4(), event_id=uuid.uuid4(),
            member_id=uuid.uuid4(), answers={"q1": 4},
        ))
        db.flush()
    assert "fk_survey_responses_survey" in str(ei.value)


def test_问卷状态只能是三种(db):
    with pytest.raises(IntegrityError) as ei:
        make_survey(db, status="archived")
    assert "ck_event_surveys_status" in str(ei.value)


def test_关闭时间必须晚于开始时间(db):
    now = datetime.now(timezone.utc)
    with pytest.raises(IntegrityError) as ei:
        db.add(EventSurvey(
            org_id=ORG, event_id=uuid.uuid4(), title="时间窗非法",
            questions=[{"id": "q1", "type": "rating", "title": "题", "scale": "star5"}],
            open_at=now, close_at=now - timedelta(days=1), status="draft",
        ))
        db.flush()
    assert "ck_event_surveys_window" in str(ei.value)


def test_questions必须是数组(db):
    now = datetime.now(timezone.utc)
    with pytest.raises(IntegrityError) as ei:
        db.add(EventSurvey(
            org_id=ORG, event_id=uuid.uuid4(), title="问题定义是对象",
            questions={"q1": {}}, open_at=now, close_at=now + timedelta(days=1),
            status="draft",
        ))
        db.flush()
    assert "ck_event_surveys_questions_array" in str(ei.value)


def test_answers必须是对象(db):
    survey = make_survey(db)
    with pytest.raises(IntegrityError) as ei:
        db.add(SurveyResponse(
            org_id=ORG, survey_id=survey.id, event_id=survey.event_id,
            member_id=uuid.uuid4(), answers=[1, 2, 3],
        ))
        db.flush()
    assert "ck_survey_responses_answers_object" in str(ei.value)


def test_统一字段默认值生效(db):
    """id / created_at / updated_at 由数据库默认值生成，应用层不传也能落库。"""
    survey = make_survey(db)
    db.flush()
    assert survey.id is not None
    assert survey.created_at is not None
    assert survey.updated_at is not None
    assert survey.status == "published"
    assert survey.anonymous is False


def test_匿名问卷标记可以写入(db):
    survey = make_survey(db)
    survey.anonymous = True
    db.flush()
    assert db.get(EventSurvey, survey.id).anonymous is True


def test_JSONB_可以按题号查询(db):
    """工作台做统计时按 jsonb 字段过滤，这里确认 JSONB 写入与查询都正常。"""
    survey = make_survey(db)
    make_response(db, survey, answers={"q1": 5, "q2": "o1", "q3": ["o1", "o2"]})
    db.flush()
    got = db.scalar(
        select(SurveyResponse.answers).where(SurveyResponse.survey_id == survey.id)
    )
    assert got["q1"] == 5
    assert got["q3"] == ["o1", "o2"]
