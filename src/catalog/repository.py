"""카탈로그 도메인 저장소."""

from __future__ import annotations

from sqlalchemy import or_, select

from src.catalog.models import Asset, AssetStatus, AssetType, McpTool
from src.shared.db.repository import _like, Repository
from src.systems.models import System


class AssetRepository(Repository[Asset]):
    model = Asset

    def catalog(self, q: str | None = None, type_: AssetType | None = None, status: AssetStatus | None = None, system_id: int | None = None) -> list[Asset]:
        stmt = select(Asset).join(System)
        if q:
            stmt = stmt.where(or_(Asset.name.ilike(_like(q)), Asset.description.ilike(_like(q)), System.name.ilike(_like(q)), System.dept.ilike(_like(q))))
        if type_:
            stmt = stmt.where(Asset.type == type_)
        if status:
            stmt = stmt.where(Asset.status == status)
        if system_id:
            stmt = stmt.where(Asset.system_id == system_id)
        return [*self.session.scalars(stmt.order_by(Asset.id)).unique()]

    def get_tool(self, asset_id: int, name: str) -> McpTool | None:
        return self.session.scalar(select(McpTool).where(McpTool.asset_id == asset_id, McpTool.name == name))
