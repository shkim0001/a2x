"""비밀번호 해시와 세션 토큰."""

import hashlib
import secrets

import bcrypt

# bcrypt는 72바이트까지만 쓴다. 넘으면 뒤가 잘려 다른 비밀번호와 같아질 수 있어 가입 단계에서 막는다.
BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        return False


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# 사용자가 없을 때도 같은 시간이 걸리도록 비교에 쓰는 가짜 해시(계정 존재 여부 노출 방지)
DUMMY_HASH = hash_password("dummy-password-for-timing")
