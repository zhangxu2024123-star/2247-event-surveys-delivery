-- event_surveys：一个活动一份问卷
-- 统一字段：id / org_id / site_id / created_at / created_by / updated_at / deleted_at
CREATE TABLE IF NOT EXISTS event_surveys (
    id          uuid        NOT NULL DEFAULT gen_random_uuid(),
    org_id      uuid        NOT NULL,
    site_id     uuid        NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    created_by  uuid        NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    deleted_at  timestamptz NULL,

    event_id    uuid        NOT NULL,
    title       text        NOT NULL,
    intro       text        NULL,
    questions   jsonb       NOT NULL,
    open_at     timestamptz NOT NULL,
    close_at    timestamptz NOT NULL,
    status      varchar(16) NOT NULL DEFAULT 'draft',
    anonymous   boolean     NOT NULL DEFAULT false,

    CONSTRAINT pk_event_surveys PRIMARY KEY (id),
    CONSTRAINT ck_event_surveys_status
        CHECK (status IN ('draft', 'published', 'closed')),
    CONSTRAINT ck_event_surveys_window
        CHECK (close_at > open_at),
    CONSTRAINT ck_event_surveys_questions_array
        CHECK (jsonb_typeof(questions) = 'array')
);

-- 一个活动只允许一份未被软删的问卷
CREATE UNIQUE INDEX IF NOT EXISTS uq_event_surveys_org_event
    ON event_surveys (org_id, event_id)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS ix_event_surveys_status
    ON event_surveys (status);

COMMENT ON TABLE  event_surveys IS '会后问卷：一个活动一份，questions 为题型 JSON 数组（见 schema/questions.schema.json）';
COMMENT ON COLUMN event_surveys.questions IS '题目定义数组，最多 20 题，4 种题型 single/multi/rating/text';
COMMENT ON COLUMN event_surveys.anonymous IS '统计时是否匿名：true 时展示层不返回 member_id';
