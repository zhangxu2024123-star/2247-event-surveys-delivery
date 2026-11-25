# 会后问卷数据表与题型 JSON Schema 校验函数（S3-MINI-065）

会员空间平台 · 会员小程序 v1 阶段的一张业务底座工单：建 `event_surveys`（一个活动一份问卷）
与 `survey_responses`（会员答卷）两张表，并提供 `validate_questions` / `validate_answers`
两个**纯函数**给工作台与小程序端共用，附 3 份虚构示例问卷的 seed 数据。

> 全部用例（58 个）跑在**真实 PostgreSQL 16 + 真实 alembic 迁移**上，不 mock 数据库；
> 实测输出见 `evidence/`。

---

## 1 交付内容

| 文件 | 说明 |
|---|---|
| `schema/event_surveys.sql` | `event_surveys` 建表 DDL（**唯一来源**，迁移与文档共用） |
| `schema/survey_responses.sql` | `survey_responses` 建表 DDL（含唯一约束与 FK 级联） |
| `schema/questions.schema.json` | `questions` 的 JSON Schema（draft 2020-12），4 种题型约束 |
| `app/models.py` | SQLAlchemy 2 ORM 映射，7 个统一字段抽成 `BaseModel` |
| `app/survey_validation.py` | `validate_questions` / `validate_answers` 纯函数（无 DB、无框架依赖） |
| `alembic/versions/20261125_01_event_surveys.py` | 迁移，直接读取上面两份 DDL |
| `data/survey_seed.json` | 3 份虚构示例问卷：活动满意度 / 嘉宾评分 / 下期主题征集 |
| `scripts/seed_surveys.py` | 幂等导入脚本（先校验再写库，支持 `--dry-run` / `--json`） |
| `tests/` | 58 个用例：定义校验 34 / 迁移 9 / 约束 15 |
| `evidence/` | 实测证据：环境、迁移往返、`alembic check`、两次导入、表结构、测试输出 |
| `docs/PR.md` | 变更说明与对接点，可直接贴进 PR |

## 2 验收标准对照

| # | 验收标准 | 实现 | 证据 |
|---|---|---|---|
| 1 | 迁移 upgrade / downgrade 均成功，`alembic check` 无漂移 | `upgrade()` 读 `schema/*.sql`；`downgrade()` 反序 DROP；`env.py` 的 `target_metadata` 指向 ORM metadata，因此 `check` 能真正比对结构 | `evidence/alembic.txt`（downgrade 后表数 0 → upgrade 后 2 → `No new upgrade operations detected`） |
| 2 | `validate_questions` 对 5 类非法定义均报错（有测试） | 题号重复 `E_DUPLICATE_QUESTION_ID`、选项 <2 `E_OPTION_COUNT`、>20 题 `E_TOO_MANY_QUESTIONS`、未知题型 `E_UNKNOWN_TYPE`、`max_length` 超限 `E_MAX_LENGTH` | `tests/test_validation.py::test_非法1~5`，共 34 个纯函数用例 |
| 3 | `validate_answers` 逐题返回必填缺失 / 多选超上限 / 评分越界 | `E_REQUIRED_MISSING` / `E_MULTI_OVER_MAX` / `E_RATING_OUT_OF_RANGE`，错误逐题收集不短路 | `tests/test_validation.py::test_非法答卷1~3` |
| 4 | 同一会员对同一问卷第二份答卷触发唯一约束 | `uq_survey_responses_survey_member UNIQUE (survey_id, member_id)` | `tests/test_constraints.py::test_同一会员同一问卷第二份答卷被唯一约束拦下`、`evidence/schema.txt` |

## 3 两张表

### 3.1 统一字段（7 个，两表都有）

`id`（uuid，`gen_random_uuid()`）、`org_id`、`site_id`、`created_at`、`created_by`、
`updated_at`、`deleted_at`（软删除，NULL = 未删）。

### 3.2 `event_surveys`

业务列：`event_id`、`title`、`intro`、`questions`(jsonb)、`open_at`、`close_at`、
`status`(draft/published/closed)、`anonymous`。

- **一个活动一份问卷**：`uq_event_surveys_org_event UNIQUE (org_id, event_id) WHERE deleted_at IS NULL`
  —— 用**部分唯一索引**，软删除后可以重建同一活动的问卷，多条租户也互不干扰；
- `open_at` 默认取活动结束时间、`close_at` 默认取结束后 7 天：由发布侧（工作台）在插入时赋值，
  本单在 `scripts/seed_surveys.py` 里用 `open_offset_days` / `close_offset_days` 演示；
- CHECK：`status` 三值、`close_at > open_at`、`jsonb_typeof(questions) = 'array'`。

### 3.3 `survey_responses`

业务列：`survey_id`(FK→`event_surveys.id` ON DELETE CASCADE)、`event_id`、`member_id`、
`signup_id`、`answers`(jsonb)、`submitted_at`、`client_version`。

- **同一会员同一问卷仅一份**：`uq_survey_responses_survey_member UNIQUE (survey_id, member_id)`；
- CHECK：`jsonb_typeof(answers) = 'object'`；
- 索引：`(event_id, member_id)`，供「某活动的答卷列表 / 会员是否已填」查询。

## 4 题型与校验规则

| 题型 | 必填字段 | 约束 |
|---|---|---|
| `single` 单选 | `options` | 2–10 项，每项含 `id`/`label`；选项 id 题内唯一 |
| `multi` 多选 | `options`、`min_select`/`max_select`（可省，默认 0 / 选项数） | 同上；`0 ≤ min ≤ max ≤ 选项数` |
| `rating` 评分 | `scale` | `star5` = 1–5 星；`nps` = 0–10 |
| `text` 文本 | `max_length` | 1–500（上限 500 由 `E_MAX_LENGTH` 兜住） |

每题：`id`（`q1`、`q2`… 问卷内唯一）、`type`、`title`、`required`(bool)、`options`、
`scale`、`max_length`、`min_select`、`max_select`。**一份问卷最多 20 题**。

两个函数都返回**错误列表**（空 = 通过），每条形如
`{"code": "E_DUPLICATE_QUESTION_ID", "path": "questions[2].id", "message": "..."}`：

```python
from app.survey_validation import validate_questions, validate_answers

errs = validate_questions(survey.questions)      # 发布前拦截
errs = validate_answers(survey.questions, ans)   # 提交前拦截，错误逐题返回
if errs:
    for e in errs:
        print(e["path"], e["code"], e["message"])
```

需要「抛异常」风格的调用方用 `assert_valid_questions` / `assert_valid_answers`，
异常对象带 `.errors` 与 `.codes()`。

## 5 环境

```
Python      3.11.18（实测；3.10.12 也跑过一遍，同样 58 passed）
PostgreSQL  16.16
SQLAlchemy  2.0.58
psycopg     3.3.9
Alembic     1.20.1
pytest      9.2.0
jsonschema  4.26.0
```

依赖清单见 `requirements.txt`，在**全新虚拟环境**里从零安装后跑通全部用例。
连接串只从环境变量读取，**不写进代码、不写进 `alembic.ini`**：

```bash
export DATABASE_URL='postgresql+psycopg://user:pass@host:5432/db'
```

## 6 怎么跑

```bash
pip install -r requirements.txt

# 1) 建表
python -m alembic upgrade head

# 2) 导入 3 份示例问卷（可重复执行，幂等）
python scripts/seed_surveys.py --dry-run   # 只校验不写库
python scripts/seed_surveys.py             # 写库：新增 3 / 更新 0
python scripts/seed_surveys.py             # 再跑一次：新增 0 / 更新 3

# 3) 测试（58 个，需要连得上 DATABASE_URL）
python -m pytest -q

# 4) 迁移自检
python -m alembic check          # 期望 No new upgrade operations detected
python -m alembic downgrade base # 回滚
python -m alembic upgrade head   # 再升级
```

> `--dry-run` 不需要数据库，只做题目定义校验，可放在 CI 的 lint 阶段。

## 7 测试说明

| 文件 | 用例数 | 覆盖 |
|---|---|---|
| `tests/test_validation.py` | 34 | 5 类非法定义、3 类非法答卷、边界（正好 20 题 / 正好 500 字 / nps 0 与 10）、JSON Schema 与运行时规则一致 |
| `tests/test_migration.py` | 9 | 迁移往返、`alembic check` 无漂移、7 个统一字段齐全、字段类型、索引与约束存在、DDL 不内联在迁移里 |
| `tests/test_constraints.py` | 15 | 唯一约束（第 4 条）、FK 级联删除、CHECK（状态/时间窗/jsonb 类型）、默认值、JSONB 读写 |

没有 `DATABASE_URL` 时，真库用例自动 skip（不会 error），纯函数用例照常跑。

## 8 对接点（给相邻工单）

| 方向 | 对接内容 |
|---|---|
| 会员小程序端 | 提交前调 `validate_answers` 做本地拦截；提交 `POST` 时带上 `client_version` |
| 工作台编辑/发布 | 保存草稿与发布前调 `validate_questions`；`status` 只允许 `draft → published → closed` |
| 活动模块 | `event_id` 由活动表提供；`open_at` 取活动结束时间、`close_at` 默认 +7 天 |
| 会员/报名模块 | `member_id`、`signup_id` 来自会员与报名表，本单只存外键值，不建跨模块 FK |
| 统计看板 | `anonymous=true` 的问卷在展示层不返回 `member_id`；聚合按 `answers` JSONB 取题号 |
| 鉴权/租户 | `org_id` 由网关注入，业务代码不要自己生成 |

## 9 边界与假设

- 只使用**虚构数据**：企业名、会员、活动均为编造，交付物中不出现客户名称；
- 依赖其他工单的接口一律以**外键值 + 桩**的方式先行，不反向建 FK（避免跨模块耦合）；
- 时间统一 `timestamptz`（UTC 存储），展示层按 `org_id` 的时区渲染；
- 软删除只改 `deleted_at`，唯一性判定用部分唯一索引，因此重建问卷/重填答卷的语义是明确的；
- 「题目说明文字不得引导会员填写」属于文案规范，示例数据已按中性措辞编写，未做机器校验。

## 10 回滚

```bash
python -m alembic downgrade base   # 删两表（survey_responses 先删，再删 event_surveys）
```

`downgrade()` 只 DROP 本单新建的两张表，不动平台既有表；外键 `ON DELETE CASCADE`
保证删问卷时答卷一并清理。
