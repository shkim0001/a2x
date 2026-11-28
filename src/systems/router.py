"""기준정보(시스템 · 서버) API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.auth.deps import current_user
from src.auth.models import User
from src.auth.schemas import UserBrief
from src.shared.db.session import get_db
from src.shared.schema import Message
from src.systems import service as svc
from src.systems.models import ServerEnv, System, SystemKind
from src.systems.repository import SystemRepository
from src.systems.schemas import ManagerIn, ServerIn, ServerOut, ServerRow, SystemIn, SystemOut, SystemUpdate


router = APIRouter(tags=["systems"])


def system_out(s: System) -> SystemOut:
    return SystemOut(
        id=s.id, code=s.code, name=s.name, kind=s.kind, process=s.process, dept=s.dept, url=s.url, data_level=s.data_level, description=s.description,
        managers=[UserBrief.model_validate(m.user) for m in s.managers],
        servers=[ServerOut.model_validate(sv) for sv in s.servers],
    )


@router.get("/systems", response_model=list[SystemOut])
def list_systems(
    q: str | None = None,
    kind: SystemKind | None = None,
    process: str | None = None,
    mine: bool = False,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return [system_out(s) for s in SystemRepository(db).search(q=q, kind=kind, process=process, managed_by=user.id if mine else None)]


@router.post("/systems", response_model=SystemOut, status_code=201)
def create_system(body: SystemIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = svc.create_system(db, user, body)
    db.commit()
    return system_out(s)


@router.get("/systems/{system_id}", response_model=SystemOut)
def get_system(system_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    return system_out(svc.get_system(db, system_id))


@router.patch("/systems/{system_id}", response_model=SystemOut)
def update_system(system_id: int, body: SystemUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = svc.update_system(db, user, system_id, body)
    db.commit()
    return system_out(s)


@router.delete("/systems/{system_id}", response_model=Message)
def delete_system(system_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    svc.delete_system(db, user, system_id)
    db.commit()
    return Message(message="삭제했습니다.")


@router.post("/systems/{system_id}/managers", response_model=SystemOut)
def add_manager(system_id: int, body: ManagerIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = svc.add_manager(db, user, system_id, body.email)
    db.commit()
    return system_out(s)


@router.delete("/systems/{system_id}/managers/{user_id}", response_model=SystemOut)
def remove_manager(system_id: int, user_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = svc.remove_manager(db, user, system_id, user_id)
    db.commit()
    return system_out(s)


@router.get("/servers", response_model=list[ServerRow])
def list_servers(
    q: str | None = None,
    env: ServerEnv | None = None,
    process: str | None = None,
    mine: bool = False,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return [
        ServerRow(**ServerOut.model_validate(sv).model_dump(), system_code=sy.code, system_name=sy.name, process=sy.process)
        for sv, sy in svc.list_servers(db, user, q, env, process, mine)
    ]


@router.post("/systems/{system_id}/servers", response_model=ServerOut, status_code=201)
def add_server(system_id: int, body: ServerIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sv = svc.add_server(db, user, system_id, body)
    db.commit()
    return ServerOut.model_validate(sv)


@router.put("/servers/{server_id}", response_model=ServerOut)
def update_server(server_id: int, body: ServerIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    sv = svc.update_server(db, user, server_id, body)
    db.commit()
    return ServerOut.model_validate(sv)


@router.delete("/servers/{server_id}", response_model=Message)
def delete_server(server_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    svc.delete_server(db, user, server_id)
    db.commit()
    return Message(message="삭제했습니다.")
