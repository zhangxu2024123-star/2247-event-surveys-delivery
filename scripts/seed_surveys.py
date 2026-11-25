#!/usr/bin/env python
"""导入 3 份虚构示例问卷（活动满意度 / 嘉宾评分 / 下期主题征集）。

* 幂等：以 ``(org_id, event_id)`` 为业务键，重复执行只更新，不产生重复行；
* 导入前用 ``app.survey_validation.validate_questions`` 逐题校验，任何一份不合法就整体回滚；
* 时间窗由 ``open_offset_days`` / ``close_offset_days`` 相对当前时间算，方便演示「已结束 → 可填」；
* 连接串只从环境变量 ``DATABASE_URL`` 读取。

用法::

    export DATABASE_URL='postgresql+psycopg://user:pass@host:5432/db'
    python scripts/seed_surveys.py --dry-run     # 只校验，不写库
    python scripts/seed_surveys.py               # 导入
    python scripts/seed_surveys.py --json        # 机器可读输出
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.models import EventSurvey  # noqa: E402
from app.survey_validation import validate_questions  # noqa: E402

SEED = ROOT / "data" / "survey_seed.json"


def load_seed() -> dict:
    return json.loads(SEED.read_text(encoding="utf-8"))


def check(seed: dict) -> list[str]:
    """返回全部错误（含 schema 级与逐题级），空列表表示可以导入。"""
    problems: list[str] = []
    for s in seed["surveys"]:
        tag = s.get("title") or s.get("event_id")
        errs = validate_questions(s.get("questions"))
        for e in errs:
            problems.append(f"{tag} :: {e['code']} @ {e['path']} :: {e['message']}")
        if not (s.get("title") or "").strip():
            problems.append(f"{tag} :: E_TITLE_REQUIRED @ title")
    return problems


def upsert(db: Session, seed: dict, base: datetime) -> tuple[int, int]:
    org_id = uuid.UUID(seed["org_id"])
    site_id = uuid.UUID(seed["site_id"]) if seed.get("site_id") else None
    created_by = uuid.UUID(seed["created_by"]) if seed.get("created_by") else None

    created = updated = 0
    for s in seed["surveys"]:
        event_id = uuid.UUID(s["event_id"])
        open_at = base + timedelta(days=s.get("open_offset_days", 0))
        close_at = base + timedelta(days=s.get("close_offset_days", 7))

        row = db.scalar(
            select(EventSurvey).where(
                EventSurvey.org_id == org_id,
                EventSurvey.event_id == event_id,
                EventSurvey.deleted_at.is_(None),
            )
        )
        if row is None:
            db.add(EventSurvey(
                org_id=org_id,
                site_id=site_id,
                created_by=created_by,
                event_id=event_id,
                title=s["title"],
                intro=s.get("intro"),
                questions=s["questions"],
                open_at=open_at,
                close_at=close_at,
                status=s.get("status", "draft"),
                anonymous=bool(s.get("anonymous", False)),
            ))
            created += 1
        else:
            row.title = s["title"]
            row.intro = s.get("intro")
            row.questions = s["questions"]
            row.open_at = open_at
            row.close_at = close_at
            row.status = s.get("status", "draft")
            row.anonymous = bool(s.get("anonymous", False))
            row.updated_at = func.now()
            updated += 1
    return created, updated


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只做校验，不连库")
    ap.add_argument("--json", action="store_true", help="输出 JSON 汇总")
    a = ap.parse_args()

    seed = load_seed()
    problems = check(seed)
    if problems:
        for p in problems:
            print("ERROR", p, file=sys.stderr)
        print(f"校验失败：{len(problems)} 处，未写库", file=sys.stderr)
        return 2

    n = len(seed["surveys"])
    if a.dry_run:
        print(f"校验通过：{n} 份问卷" + ("（dry-run，未写库）" if a.dry_run else ""))
        return 0

    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        print("ERROR: 请先设置 DATABASE_URL", file=sys.stderr)
        return 2

    base = datetime.now(timezone.utc).replace(microsecond=0)
    engine = create_engine(url, future=True)
    with Session(engine) as db:
        created, updated = upsert(db, seed, base)
        db.commit()
        total = db.scalar(select(func.count()).select_from(EventSurvey)) or 0

    out = {
        "validated": n,
        "created": created,
        "updated": updated,
        "event_surveys_total": total,
        "base_time_utc": base.isoformat(),
    }
    if a.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"校验通过：{n} 份问卷")
        print(f"导入完成：新增 {created} / 更新 {updated} / 表内合计 {total} 行")
        print(f"时间基准（UTC）：{base.isoformat()}")
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
