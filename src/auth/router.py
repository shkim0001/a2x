from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.auth import google as google_auth, service as auth_service
from src.auth.deps import current_user, read_token, SESSION_COOKIE
from src.auth.models import Role, User
from src.auth.schemas import LoginIn, MeOut, ProvidersOut, RoleSwitchIn, SessionOut, SignupIn, UserOut
from src.shared.config import dev_role_switch_enabled, settings
from src.shared.db.session import get_db
from src.shared.errors import ServiceError
from src.shared.schema import Message
from src.systems.access import effective_role

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        samesite="lax",
        secure=not settings.DEBUG,
        path="/",
    )


def _session_out(db: Session, user: User, token: str) -> SessionOut:
    return SessionOut(user=UserOut.model_validate(user), effective_role=effective_role(db, user), token=token)


@router.post("/signup", response_model=SessionOut, status_code=201)
def signup(body: SignupIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = auth_service.signup(db, body.email, body.name, body.password)
    token, _ = auth_service.create_session(db, user, request.headers.get("user-agent", ""))
    db.commit()
    _set_cookie(response, token)
    return _session_out(db, user, token)


@router.post("/login", response_model=SessionOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, body.email, body.password)
    token, _ = auth_service.create_session(db, user, request.headers.get("user-agent", ""))
    db.commit()
    _set_cookie(response, token)
    return _session_out(db, user, token)


@router.post("/logout", response_model=Message)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    auth_service.logout(db, read_token(request))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return Message(message="로그아웃했습니다.")


def _me(db: Session, user: User) -> MeOut:
    from src.systems.repository import SystemRepository

    return MeOut(user=UserOut.model_validate(user), effective_role=effective_role(db, user), managed_system_ids=sorted(SystemRepository(db).managed_ids(user.id)))


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _me(db, user)


@router.put("/dev/role", response_model=MeOut)
def switch_role(body: RoleSwitchIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """개발용 권한 스위치(개발 환경에서만). 바뀐 내 정보를 돌려준다."""
    auth_service.switch_role_dev(db, user, Role(body.role))
    db.commit()
    return _me(db, user)


# ---------- Google 로그인 (T1-4) ----------


def get_google() -> google_auth.GoogleOAuth:
    return google_auth.default_client()


def _to_portal(error: str | None = None) -> RedirectResponse:
    url = settings.FRONTEND_URL + (("&" if "?" in settings.FRONTEND_URL else "?") + urlencode({"login_error": error}) if error else "")
    resp = RedirectResponse(url, status_code=303)
    resp.delete_cookie(google_auth.STATE_COOKIE, path="/api/v1/auth/google")
    return resp


@router.get("/providers", response_model=ProvidersOut)
def providers():
    """로그인 화면이 쓸 수 있는 외부 로그인(설정된 것만)."""
    return ProvidersOut(google=google_auth.configured(), dev_role_switch=dev_role_switch_enabled())


@router.get("/google/login")
def google_login(google: google_auth.GoogleOAuth = Depends(get_google)):
    if not google_auth.configured():
        return _to_portal("google_not_configured")
    url, state, verifier = google.authorization_url()
    resp = RedirectResponse(url, status_code=303)
    resp.set_cookie(google_auth.STATE_COOKIE, google_auth.pack_state(state, verifier), max_age=google_auth.STATE_TTL,
                    httponly=True, samesite="lax", secure=not settings.DEBUG, path="/api/v1/auth/google")
    return resp


@router.get("/google/callback")
async def google_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
                          db: Session = Depends(get_db), google: google_auth.GoogleOAuth = Depends(get_google)):
    """Google이 돌려보낸 요청. 성공하면 세션 쿠키를 붙여 포탈로, 실패하면 login_error와 함께 포탈 로그인 화면으로."""
    if error:
        return _to_portal("google_denied" if error == "access_denied" else "google_error")
    try:
        verifier = google_auth.unpack_state(request.cookies.get(google_auth.STATE_COOKIE), state)
        if not code:
            raise google_auth.GoogleAuthError("code_missing")
        info = await google.fetch_userinfo(code, verifier)
        user = google_auth.login_with_google(db, info)
        token, _ = auth_service.create_session(db, user, request.headers.get("user-agent", ""))
        db.commit()
    except google_auth.GoogleAuthError as e:
        db.rollback()
        return _to_portal(e.code)
    except ServiceError as e:
        db.rollback()
        return _to_portal(e.code)
    resp = _to_portal()
    _set_cookie(resp, token)
    return resp
