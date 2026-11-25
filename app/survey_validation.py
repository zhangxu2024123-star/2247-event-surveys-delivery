"""会后问卷题型校验（纯函数，无数据库、无框架依赖）。

后端工作台（编辑/发布）与小程序端（提交前自检）共用这两个函数：

* ``validate_questions(questions)`` —— 校验一份问卷的 ``questions`` 定义；
* ``validate_answers(questions, answers)`` —— 校验会员提交的 ``answers``。

两者都**返回错误列表**（空列表 = 通过），元素形如::

    {"code": "E_DUPLICATE_QUESTION_ID", "path": "questions[2].id", "message": "..."}

需要「抛异常」风格的调用方用 ``assert_valid_questions`` / ``assert_valid_answers``。

非法定义覆盖（对应验收标准第 2 条）：
1. 题号重复            -> ``E_DUPLICATE_QUESTION_ID``
2. 选择题选项少于 2 个  -> ``E_OPTION_COUNT``
3. 超过 20 题          -> ``E_TOO_MANY_QUESTIONS``
4. 未知题型            -> ``E_UNKNOWN_TYPE``
5. ``max_length`` 超限 -> ``E_MAX_LENGTH``

答案校验覆盖（对应验收标准第 3 条）：
1. 必填缺失            -> ``E_REQUIRED_MISSING``
2. 多选超过上限        -> ``E_MULTI_OVER_MAX``
3. 评分越界            -> ``E_RATING_OUT_OF_RANGE``

错误一律**逐题返回**，不在第一个错误处短路，方便工作台一次性把问题标红。
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

__all__ = [
    "QUESTION_TYPES",
    "MAX_QUESTIONS",
    "MAX_OPTIONS",
    "MIN_OPTIONS",
    "MAX_TEXT_LENGTH",
    "RATING_SCALES",
    "SurveyValidationError",
    "validate_questions",
    "validate_answers",
    "assert_valid_questions",
    "assert_valid_answers",
    "compare",
]

QUESTION_TYPES = ("single", "multi", "rating", "text")
MAX_QUESTIONS = 20
MIN_OPTIONS = 2
MAX_OPTIONS = 10
MAX_TEXT_LENGTH = 500
RATING_SCALES = {"star5": (1, 5), "nps": (0, 10)}

_QUESTION_ID_RE = re.compile(r"^q[1-9][0-9]*$")


class SurveyValidationError(ValueError):
    """校验失败。``errors`` 与 ``validate_*`` 的返回值结构一致。"""

    def __init__(self, errors: list[dict[str, str]]):
        self.errors = errors
        head = errors[0]["message"] if errors else "校验失败"
        super().__init__(f"{len(errors)} 处校验失败：{head}")

    def codes(self) -> list[str]:
        return [e["code"] for e in self.errors]


# --------------------------------------------------------------- 内部工具

def _err(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def _is_int(v: Any) -> bool:
    """bool 是 int 的子类，评分里必须排除，否则 True 会被当成 1 分。"""
    return isinstance(v, int) and not isinstance(v, bool)


def _non_empty_str(v: Any) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False


def _check_option_list(q: dict, path: str, errors: list[dict[str, str]]) -> list[str]:
    """返回可用选项 id 列表；同时把选项层面的问题写进 errors。"""
    options = q.get("options")
    if not isinstance(options, list):
        errors.append(_err("E_OPTION_COUNT", f"{path}.options",
                           "选择题必须提供 options 数组"))
        return []
    n = len(options)
    if n < MIN_OPTIONS or n > MAX_OPTIONS:
        errors.append(_err("E_OPTION_COUNT", f"{path}.options",
                           f"选项数必须在 {MIN_OPTIONS}–{MAX_OPTIONS} 之间，当前 {n} 个"))

    ids: list[str] = []
    for i, opt in enumerate(options):
        op = f"{path}.options[{i}]"
        if not isinstance(opt, dict):
            errors.append(_err("E_OPTION_NOT_OBJECT", op, "选项必须是对象（含 id 与 label）"))
            continue
        oid = opt.get("id")
        if not _non_empty_str(oid):
            errors.append(_err("E_OPTION_ID_REQUIRED", f"{op}.id", "选项 id 不能为空"))
        elif oid in ids:
            errors.append(_err("E_DUPLICATE_OPTION_ID", f"{op}.id", f"选项 id 重复：{oid}"))
        else:
            ids.append(oid)
        if not _non_empty_str(opt.get("label")):
            errors.append(_err("E_OPTION_LABEL_REQUIRED", f"{op}.label", "选项 label 不能为空"))
    return ids


# --------------------------------------------------------------- 问卷定义

def validate_questions(questions: Any) -> list[dict[str, str]]:
    """校验问卷题目定义，返回错误列表（空 = 通过）。"""
    errors: list[dict[str, str]] = []

    if not isinstance(questions, list):
        return [_err("E_QUESTIONS_NOT_ARRAY", "questions", "questions 必须是数组")]

    if len(questions) == 0:
        errors.append(_err("E_NO_QUESTIONS", "questions", "问卷至少要有 1 道题"))

    if len(questions) > MAX_QUESTIONS:
        errors.append(_err("E_TOO_MANY_QUESTIONS", "questions",
                           f"一份问卷最多 {MAX_QUESTIONS} 题，当前 {len(questions)} 题"))

    seen: dict[str, int] = {}
    for idx, q in enumerate(questions):
        path = f"questions[{idx}]"
        if not isinstance(q, dict):
            errors.append(_err("E_QUESTION_NOT_OBJECT", path, "题目必须是对象"))
            continue

        # ---- id：q1、q2…，问卷内唯一
        qid = q.get("id")
        if not _non_empty_str(qid):
            errors.append(_err("E_QUESTION_ID_REQUIRED", f"{path}.id", "题号 id 不能为空"))
        elif not _QUESTION_ID_RE.match(qid):
            errors.append(_err("E_INVALID_QUESTION_ID", f"{path}.id",
                               f"题号格式必须是 q1、q2…，当前 {qid!r}"))
        elif qid in seen:
            errors.append(_err("E_DUPLICATE_QUESTION_ID", f"{path}.id",
                               f"题号重复：{qid}（与 questions[{seen[qid]}] 相同）"))
        else:
            seen[qid] = idx

        # ---- type
        qtype = q.get("type")
        if not _non_empty_str(qtype):
            errors.append(_err("E_MISSING_FIELD", f"{path}.type", "缺少题型 type"))
            continue
        if qtype not in QUESTION_TYPES:
            errors.append(_err("E_UNKNOWN_TYPE", f"{path}.type",
                               f"未知题型 {qtype!r}，只支持 {'/'.join(QUESTION_TYPES)}"))
            continue

        # ---- title / required
        if not _non_empty_str(q.get("title")):
            errors.append(_err("E_TITLE_REQUIRED", f"{path}.title", "题干 title 不能为空"))
        if "required" in q and not isinstance(q["required"], bool):
            errors.append(_err("E_REQUIRED_NOT_BOOL", f"{path}.required",
                               "required 必须是布尔值"))

        # ---- 分题型细节
        if qtype in ("single", "multi"):
            opt_ids = _check_option_list(q, path, errors)
            if qtype == "multi":
                _check_select_range(q, path, len(opt_ids), errors)
        elif qtype == "rating":
            scale = q.get("scale")
            if scale not in RATING_SCALES:
                errors.append(_err("E_RATING_SCALE", f"{path}.scale",
                                   f"评分题 scale 必须是 {'/'.join(RATING_SCALES)}，当前 {scale!r}"))
        elif qtype == "text":
            ml = q.get("max_length")
            if ml is None:
                errors.append(_err("E_MISSING_FIELD", f"{path}.max_length",
                                   "文本题必须给出 max_length"))
            elif not _is_int(ml) or ml <= 0:
                errors.append(_err("E_INVALID_MAX_LENGTH", f"{path}.max_length",
                                   f"max_length 必须是正整数，当前 {ml!r}"))
            elif ml > MAX_TEXT_LENGTH:
                errors.append(_err("E_MAX_LENGTH", f"{path}.max_length",
                                   f"max_length 上限 {MAX_TEXT_LENGTH}，当前 {ml}"))

    return errors


def _check_select_range(q: dict, path: str, option_count: int,
                        errors: list[dict[str, str]]) -> None:
    mn = q.get("min_select", 0)
    mx = q.get("max_select", option_count)
    if not _is_int(mn) or mn < 0:
        errors.append(_err("E_SELECT_RANGE", f"{path}.min_select",
                           f"min_select 必须是非负整数，当前 {mn!r}"))
        return
    if not _is_int(mx) or mx < 1:
        errors.append(_err("E_SELECT_RANGE", f"{path}.max_select",
                           f"max_select 必须是正整数，当前 {mx!r}"))
        return
    if mn > mx:
        errors.append(_err("E_SELECT_RANGE", path,
                           f"min_select({mn}) 不能大于 max_select({mx})"))
    if option_count and mx > option_count:
        errors.append(_err("E_SELECT_RANGE", f"{path}.max_select",
                           f"max_select({mx}) 超过选项数({option_count})"))


# --------------------------------------------------------------- 答卷

def validate_answers(questions: Any, answers: Any) -> list[dict[str, str]]:
    """逐题校验答卷，返回错误列表（空 = 通过）。"""
    errors: list[dict[str, str]] = []

    if not isinstance(questions, list):
        return [_err("E_QUESTIONS_NOT_ARRAY", "questions", "questions 必须是数组")]
    if not isinstance(answers, dict):
        return [_err("E_ANSWERS_NOT_OBJECT", "answers", "answers 必须是以题号为键的对象")]

    known = {q.get("id") for q in questions if isinstance(q, dict) and _non_empty_str(q.get("id"))}
    for key in answers:
        if key not in known:
            errors.append(_err("E_UNKNOWN_QUESTION", f"answers.{key}",
                               f"答卷里出现了问卷中没有的题号 {key!r}"))

    for idx, q in enumerate(questions):
        if not isinstance(q, dict) or not _non_empty_str(q.get("id")):
            continue
        qid = q["id"]
        path = f"answers.{qid}"
        qtype = q.get("type")
        required = q.get("required") is True
        value = answers.get(qid)

        if _is_empty(value):
            if required:
                errors.append(_err("E_REQUIRED_MISSING", path, f"必填题 {qid} 未作答"))
            continue

        if qtype == "single":
            opt_ids = [o.get("id") for o in (q.get("options") or []) if isinstance(o, dict)]
            if not isinstance(value, str):
                errors.append(_err("E_INVALID_ANSWER_TYPE", path,
                                   "单选题答案必须是选项 id 字符串"))
            elif value not in opt_ids:
                errors.append(_err("E_INVALID_OPTION", path,
                                   f"选项 {value!r} 不在本题选项内"))
        elif qtype == "multi":
            opt_ids = [o.get("id") for o in (q.get("options") or []) if isinstance(o, dict)]
            mx = q.get("max_select", len(opt_ids))
            mn = q.get("min_select", 0)
            if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
                errors.append(_err("E_INVALID_ANSWER_TYPE", path,
                                   "多选题答案必须是选项 id 字符串数组"))
                continue
            bad = [v for v in value if v not in opt_ids]
            if bad:
                errors.append(_err("E_INVALID_OPTION", path,
                                   f"选项 {bad} 不在本题选项内"))
            dup = {v for v in value if value.count(v) > 1}
            if dup:
                errors.append(_err("E_DUPLICATE_ANSWER_OPTION", path,
                                   f"同一选项重复提交：{sorted(dup)}"))
            if _is_int(mx) and len(value) > mx:
                errors.append(_err("E_MULTI_OVER_MAX", path,
                                   f"最多选 {mx} 项，当前 {len(value)} 项"))
            if _is_int(mn) and len(value) < mn:
                errors.append(_err("E_MULTI_UNDER_MIN", path,
                                   f"至少选 {mn} 项，当前 {len(value)} 项"))
        elif qtype == "rating":
            lo, hi = RATING_SCALES.get(q.get("scale"), (None, None))
            if not _is_int(value):
                errors.append(_err("E_INVALID_ANSWER_TYPE", path,
                                   "评分必须是整数"))
            elif lo is not None and not (lo <= value <= hi):
                errors.append(_err("E_RATING_OUT_OF_RANGE", path,
                                   f"评分必须在 {lo}–{hi} 之间（scale={q.get('scale')}），当前 {value}"))
        elif qtype == "text":
            ml = q.get("max_length") or MAX_TEXT_LENGTH
            if not isinstance(value, str):
                errors.append(_err("E_INVALID_ANSWER_TYPE", path, "文本题答案必须是字符串"))
            elif _is_int(ml) and len(value) > ml:
                errors.append(_err("E_TEXT_TOO_LONG", path,
                                   f"最多 {ml} 字，当前 {len(value)} 字"))

    return errors


def assert_valid_questions(questions: Any) -> None:
    errs = validate_questions(questions)
    if errs:
        raise SurveyValidationError(errs)


def assert_valid_answers(questions: Any, answers: Any) -> None:
    errs = validate_answers(questions, answers)
    if errs:
        raise SurveyValidationError(errs)


def compare(expected: Sequence[dict], actual: Iterable[dict]) -> bool:
    """测试辅助：不关心顺序地比较错误集合。"""
    key = lambda e: (e["code"], e["path"])  # noqa: E731
    return sorted(map(key, expected)) == sorted(map(key, actual))
