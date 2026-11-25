-- survey_responses：会员答卷
-- 统一字段：id / org_id / site_id / created_at / created_by / updated_at / deleted_at
CREATE TABLE IF NOT EXISTS survey_responses (
    id             uuid        NOT NULL DEFAULT gen_random_uuid(),
    org_id         uuid        NOT NULL,
    site_id        uuid        NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),
    created_by     uuid        NULL,
    updated_at     timestamptz NOT NULL DEFAULT now(),
    deleted_at     timestamptz NULL,

    survey_id      uuid        NOT NULL,
    event_id       uuid        NOT NULL,
    member_id      uuid        NOT NULL,
    signup_id      uuid        NULL,
    answers        jsonb       NOT NULL,
    submitted_at   timestamptz NOT NULL DEFAULT now(),
    client_version varchar(32) NULL,

    CONSTRAINT pk_survey_responses PRIMARY KEY (id),
    CONSTRAINT fk_survey_responses_survey
        FOREIGN KEY (survey_id) REFERENCES event_surveys (id) ON DELETE CASCADE,
    CONSTRAINT uq_survey_responses_survey_member UNIQUE (survey_id, member_id),
    CONSTRAINT ck_survey_responses_answers_object
        CHECK (jsonb_typeof(answers) = 'object')
);

CREATE INDEX IF NOT EXISTS ix_survey_responses_event_member
    ON survey_responses (event_id, member_id);

COMMENT ON TABLE  survey_responses IS '会员答卷：同一会员对同一问卷仅一份（uq_survey_responses_survey_member）';
COMMENT ON COLUMN survey_responses.answers IS '以题号为键的答案对象，如 {"q1": "o1", "q2": ["o1","o3"], "q3": 5}';
COMMENT ON COLUMN survey_responses.client_version IS '小程序/工作台客户端版本号，便于排查提交异常';
