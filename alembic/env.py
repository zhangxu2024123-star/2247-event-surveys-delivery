"""alembic 环境：连接串只从环境变量 DATABASE_URL 读取，不写死在配置里。

平台仓库已有自己的 alembic 环境，本文件只是让本单可以独立跑
``alembic upgrade head`` / ``alembic downgrade base`` / ``alembic check`` 复现迁移。

``target_metadata`` 指向 ``app.models.Base.metadata``，因此 ``alembic check`` 能真正
比对「迁移建出来的表」与「ORM 声明的表」是否零漂移 —— 这是验收标准第 1 条的判据。
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import Base  # noqa: E402  (需要先插入 sys.path)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise SystemExit("ERROR: 请先设置环境变量 DATABASE_URL（alembic 不读配置文件里的口令）")

target_metadata = Base.metadata


def _include_object(obj, name, type_, reflected, compare_to):  # noqa: ANN001
    """忽略 alembic 自己的版本表。"""
    if type_ == "table" and name == "alembic_version":
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        include_object=_include_object,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(DATABASE_URL, poolclass=pool.NullPool, future=True)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=_include_object,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
