# PR：会后问卷数据表与题型 JSON Schema 校验函数（S3-MINI-065）

## 变更内容

1. **新增两张表**（7 个统一字段齐全）
   - `event_surveys`：一个活动一份问卷，`questions` 存题型 JSONB 数组；
   - `survey_responses`：会员答卷，`UNIQUE (survey_id, member_id)` 保证一人一份。
2. **新增两个纯函数**（工作台与小程序端共用，无 DB / 无框架依赖）
   - `validate_questions(questions)`：发布前拦截非法定义，覆盖 5 类必检错误；
   - `validate_answers(questions, answers)`：提交前逐题校验，覆盖必填缺失 / 多选超上限 / 评分越界。
3. **新增 `schema/questions.schema.json`**：`questions` 的 JSON Schema（draft 2020-12），
   与运行时校验规则一致（用例断言两者常量相等）。
4. **新增迁移** `20261125_01`：直接读取 `schema/*.sql`，DDL 单一来源；
   `downgrade()` 反序 DROP，可完整回滚。
5. **新增 seed 脚本与 3 份虚构示例问卷**：活动满意度（4 题，含 5 星评分 + 多选 + 文本）、
   嘉宾评分（5 题，含 nps 0–10）、下期主题征集（4 题，草稿态）。

## 为什么这样拆

- **DDL 放 `schema/*.sql`，迁移只读文件**：本单是 1500 个工单之一，后续工单大概率要改这两张表；
  DDL、迁移、README、测试若各写一份必然漂移（上一批工单踩过），所以只保留一处来源。
- **校验写成纯函数**：小程序端要在提交前本地拦一次，后端要再拦一次；抽成无依赖模块两边共用，
  避免「前端一套规则、后端一套规则」。
- **错误逐题返回而不短路**：工作台需要一次把所有问题标红，而不是改一个再报一个。
- **`event_id` 唯一性用部分唯一索引（`WHERE deleted_at IS NULL`）**：软删除后允许重建同一活动的问卷，
  同时不破坏多租户（`org_id` 参与唯一键）。

## 复现命令

```bash
export DATABASE_URL='postgresql+psycopg://user:pass@host:5432/db'

python -m alembic upgrade head
python -m pytest -q                 # 58 passed
python -m alembic check             # No new upgrade operations detected
python scripts/seed_surveys.py      # 新增 3；再跑一次 更新 3（幂等）
```

## 对接点

- 活动模块：`event_id`、`open_at`（活动结束时间）、`close_at`（默认 +7 天）由发布侧赋值；
- 会员/报名模块：`member_id`、`signup_id` 只存外键值，不建跨模块 FK；
- 统计看板：`anonymous=true` 的问卷展示层不返回 `member_id`；
- 网关：`org_id` 由网关注入，业务代码不自行生成。

## 风险与已知取舍

- 未做「同一问卷并发提交」的额外行锁：唯一约束已能兜住重复提交，冲突时返回 409 由端上提示；
- 题目文案是否「引导会员填写」属内容规范，未做机器校验，示例数据按中性措辞编写；
- `questions` 的 JSON Schema 与运行时函数是两套实现，用一条用例锁定常量一致（20 题 / 500 字 / 2–10 选项），
  换规则时两处必须同改 —— 这是刻意保留的双保险。
