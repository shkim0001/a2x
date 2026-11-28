"""저장 역할을 admin · 일반만 남긴다(시스템 담당자는 담당 시스템 유무로 계산).

Revision ID: 7c1e2a9d4b10
Revises: 160d5b33c17a
Create Date: 2026-11-25

users.role의 CHECK 제약은 그대로 둔다(SQLite에서 users 테이블을 다시 만들면 FK 연쇄 삭제 위험). 값만 MANAGER → USER로 바꾼다.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "7c1e2a9d4b10"
down_revision: Union[str, Sequence[str], None] = "160d5b33c17a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET role = 'USER' WHERE role = 'MANAGER'")


def downgrade() -> None:
    # 담당 시스템이 있는 일반 사용자를 예전처럼 MANAGER로 되돌린다
    op.execute("UPDATE users SET role = 'MANAGER' WHERE role = 'USER' AND id IN (SELECT user_id FROM system_managers)")
