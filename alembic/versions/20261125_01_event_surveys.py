"""创建会后问卷两表：event_surveys / survey_responses

DDL 单一来源：``schema/event_surveys.sql`` 与 ``schema/survey_responses.sql``
（迁移直接读取这两个文件，避免迁移 / 文档 / 测试三处漂移）。

Revision: 20261125_01
Create Date: 2026-11-25 12:30:00
"""

from __future__ import annotations

import pathlib

from alembic import op

revision = "20261125_01"
down_revision = None
branch_labels = None
depends_on = None

_SCHEMA = pathlib.Path(__file__).resolve().parents[2] / "schema"
_UP = ("event_surveys.sql", "survey_responses.sql")


def upgrade() -> None:
    for name in _UP:
        op.execute((_SCHEMA / name).read_text(encoding="utf-8"))


def downgrade() -> None:
    # 反向顺序：先删子表（有 FK），再删父表；索引随表一起删
    op.execute("DROP TABLE IF EXISTS survey_responses")
    op.execute("DROP TABLE IF EXISTS event_surveys")
