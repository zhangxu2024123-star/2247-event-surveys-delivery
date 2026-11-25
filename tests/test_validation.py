"""验收标准第 2、3 条：非法定义 5 类、非法答卷 3 类，逐条报错。

本文件是纯函数用例，**不连库**，可在任何环境跑。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.survey_validation import (
    MAX_QUESTIONS,
    MAX_TEXT_LENGTH,
    SurveyValidationError,
    assert_valid_answers,
    assert_valid_questions,
    validate_answers,
    validate_questions,
)

ROOT = Path(__file__).resolve().parent.parent


def load_seed():
    return json.loads((ROOT / "data" / "survey_seed.json").read_text(encoding="utf-8"))


def base_questions():
    return [
        {"id": "q1", "type": "rating", "title": "整体满意度", "required": True, "scale": "star5"},
        {"id": "q2", "type": "single", "title": "参与方式", "required": True,
         "options": [{"id": "o1", "label": "现场"}, {"id": "o2", "label": "线上"}]},
        {"id": "q3", "type": "multi", "title": "帮助较大的环节", "required": False,
         "min_select": 1, "max_select": 2,
         "options": [{"id": "o1", "label": "分享"}, {"id": "o2", "label": "洽谈"},
                     {"id": "o3", "label": "参观"}]},
        {"id": "q4", "type": "text", "title": "建议", "required": False, "max_length": 200},
    ]


def codes(errors):
    return {e["code"] for e in errors}


# ---------------------------------------------------------------- 合法基线

def test_合法定义零错误():
    assert validate_questions(base_questions()) == []


def test_三份示例问卷全部合法():
    seed = load_seed()
    assert len(seed["surveys"]) == 3
    for s in seed["surveys"]:
        assert validate_questions(s["questions"]) == [], s["title"]


def test_四道题对应四种题型():
    types = [q["type"] for q in base_questions()]
    assert types == ["rating", "single", "multi", "text"]


# ---------------------------------------------------- 验收标准第 2 条：5 类非法定义

def test_非法1_题号重复():
    qs = base_questions()
    qs[1]["id"] = "q1"
    errs = validate_questions(qs)
    assert "E_DUPLICATE_QUESTION_ID" in codes(errs)
    assert errs[0]["path"] == "questions[1].id"


def test_非法2_选择题选项少于两个():
    qs = base_questions()
    qs[1]["options"] = [{"id": "o1", "label": "唯一选项"}]
    errs = validate_questions(qs)
    assert "E_OPTION_COUNT" in codes(errs)
    assert "2–10" in [e for e in errs if e["code"] == "E_OPTION_COUNT"][0]["message"]


def test_非法2b_多选题选项只有一个也报错():
    qs = base_questions()
    qs[2]["options"] = [{"id": "o1", "label": "唯一选项"}]
    assert "E_OPTION_COUNT" in codes(validate_questions(qs))


def test_非法3_超过20题():
    qs = base_questions()
    for i in range(5, MAX_QUESTIONS + 2):        # 4 + 17 = 21 题
        qs.append({"id": f"q{i}", "type": "rating", "title": f"题 {i}", "scale": "star5"})
    errs = validate_questions(qs)
    assert "E_TOO_MANY_QUESTIONS" in codes(errs)
    assert len(qs) == MAX_QUESTIONS + 1


def test_非法3b_恰好20题不报错():
    qs = base_questions()
    for i in range(5, MAX_QUESTIONS + 1):        # 补齐到正好 20 题
        qs.append({"id": f"q{i}", "type": "rating", "title": f"题 {i}", "scale": "star5"})
    assert len(qs) == MAX_QUESTIONS
    assert "E_TOO_MANY_QUESTIONS" not in codes(validate_questions(qs))


def test_非法4_未知题型():
    qs = base_questions()
    qs[0]["type"] = "matrix"
    errs = validate_questions(qs)
    assert "E_UNKNOWN_TYPE" in codes(errs)


def test_非法5_max_length超限():
    qs = base_questions()
    qs[3]["max_length"] = MAX_TEXT_LENGTH + 1
    errs = validate_questions(qs)
    assert "E_MAX_LENGTH" in codes(errs)


def test_非法5b_max_length非正整数():
    qs = base_questions()
    qs[3]["max_length"] = 0
    assert "E_INVALID_MAX_LENGTH" in codes(validate_questions(qs))


def test_非法6_题号格式不对():
    qs = base_questions()
    qs[0]["id"] = "Q1"
    assert "E_INVALID_QUESTION_ID" in codes(validate_questions(qs))


def test_非法7_评分题scale缺失():
    qs = base_questions()
    del qs[0]["scale"]
    assert "E_RATING_SCALE" in codes(validate_questions(qs))


def test_非法8_多选上下限矛盾():
    qs = base_questions()
    qs[2]["min_select"] = 3
    qs[2]["max_select"] = 2
    assert "E_SELECT_RANGE" in codes(validate_questions(qs))


def test_非法9_选项id重复():
    qs = base_questions()
    qs[1]["options"] = [{"id": "o1", "label": "现场"}, {"id": "o1", "label": "线上"}]
    assert "E_DUPLICATE_OPTION_ID" in codes(validate_questions(qs))


def test_非法10_一次给出多个错误不短路():
    qs = base_questions()
    qs[0]["type"] = "matrix"          # 未知题型
    qs[1]["options"] = [{"id": "o1", "label": "唯"}]
    qs[3]["max_length"] = 900         # 超限
    errs = validate_questions(qs)
    assert {"E_UNKNOWN_TYPE", "E_OPTION_COUNT", "E_MAX_LENGTH"} <= codes(errs)


def test_非数组直接报错():
    assert codes(validate_questions("q1")) == {"E_QUESTIONS_NOT_ARRAY"}
    assert codes(validate_questions([])) == {"E_NO_QUESTIONS"}


# ---------------------------------------------------- 验收标准第 3 条：3 类非法答卷

def test_非法答卷1_必填缺失():
    errs = validate_answers(base_questions(), {"q2": "o1"})   # 缺必答的 q1
    assert "E_REQUIRED_MISSING" in codes(errs)
    assert any(e["path"] == "answers.q1" for e in errs)


def test_非法答卷1b_必填但答空串也算缺失():
    errs = validate_answers(base_questions(), {"q1": 4, "q2": "   "})
    assert "E_REQUIRED_MISSING" in codes(errs)


def test_非法答卷2_多选超过上限():
    errs = validate_answers(base_questions(),
                            {"q1": 5, "q2": "o1", "q3": ["o1", "o2", "o3"]})
    assert codes(errs) == {"E_MULTI_OVER_MAX"}
    assert "最多选 2 项" in errs[0]["message"]


def test_非法答卷3_评分越界():
    errs = validate_answers(base_questions(),
                            {"q1": 6, "q2": "o1"})
    assert codes(errs) == {"E_RATING_OUT_OF_RANGE"}
    assert "1–5" in errs[0]["message"]


def test_非法答卷3b_nps越界():
    qs = [{"id": "q1", "type": "rating", "title": "推荐意愿", "required": True, "scale": "nps"}]
    assert codes(validate_answers(qs, {"q1": 11})) == {"E_RATING_OUT_OF_RANGE"}
    assert validate_answers(qs, {"q1": 0}) == []
    assert validate_answers(qs, {"q1": 10}) == []


def test_非法答卷_多选题数不足():
    qs = base_questions()
    qs[2]["required"] = True
    qs[2]["min_select"] = 2
    errs = validate_answers(qs, {"q1": 4, "q2": "o1", "q3": ["o1"]})
    assert codes(errs) == {"E_MULTI_UNDER_MIN"}


def test_可选多选题答空数组视为未作答():
    errs = validate_answers(base_questions(), {"q1": 4, "q2": "o1", "q3": []})
    assert errs == []


def test_非法答卷_选项不在本题目内():
    errs = validate_answers(base_questions(), {"q1": 4, "q2": "o9"})
    assert codes(errs) == {"E_INVALID_OPTION"}


def test_非法答卷_文本超长():
    qs = [{"id": "q1", "type": "text", "title": "建议", "required": False, "max_length": 5}]
    assert codes(validate_answers(qs, {"q1": "六个字符啊啊啊"})) == {"E_TEXT_TOO_LONG"}


def test_非法答卷_出现问卷里没有的题号():
    errs = validate_answers(base_questions(), {"q1": 4, "q2": "o1", "q99": "x"})
    assert "E_UNKNOWN_QUESTION" in codes(errs)


def test_非法答卷_评分给布尔值被拒():
    # bool 是 int 子类，必须挡住，否则 True 会被当成 1 分
    assert "E_INVALID_ANSWER_TYPE" in codes(validate_answers(base_questions(), {"q1": True, "q2": "o1"}))


def test_合法答卷零错误():
    ans = {"q1": 5, "q2": "o2", "q3": ["o1", "o3"], "q4": "多办几场"}
    assert validate_answers(base_questions(), ans) == []


def test_可选题目整题不答也能通过():
    assert validate_answers(base_questions(), {"q1": 3, "q2": "o1"}) == []


# ---------------------------------------------------------------- 抛异常风格

def test_断言函数抛异常且带错误明细():
    with pytest.raises(SurveyValidationError) as ei:
        assert_valid_questions([{"id": "q1", "type": "matrix", "title": "题"}])
    assert "E_UNKNOWN_TYPE" in ei.value.codes()


def test_断言函数在合法输入上不抛异常():
    assert_valid_questions(base_questions())
    assert_valid_answers(base_questions(), {"q1": 4, "q2": "o1"})


# ---------------------------------------------------------------- 与 JSON Schema 对齐

def test_json_schema_能加载且约束与常量一致():
    schema = json.loads((ROOT / "schema" / "questions.schema.json").read_text(encoding="utf-8"))
    assert schema["maxItems"] == MAX_QUESTIONS
    assert schema["items"]["$ref"] == "#/$defs/question"
    assert schema["$defs"]["question"]["properties"]["max_length"]["maximum"] == MAX_TEXT_LENGTH
    assert schema["$defs"]["question"]["properties"]["options"]["minItems"] == 2
    assert schema["$defs"]["question"]["properties"]["options"]["maxItems"] == 10


def test_json_schema_校验合法与非法样本():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((ROOT / "schema" / "questions.schema.json").read_text(encoding="utf-8"))
    jsonschema.validate(base_questions(), schema)

    bad = base_questions()
    bad[3]["max_length"] = 999
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
