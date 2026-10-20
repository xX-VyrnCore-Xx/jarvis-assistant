import secrets

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings
from .security import AuthThrottle, client_ip

_bearer = HTTPBearer(auto_error=False)
throttle = AuthThrottle()


def require_token(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.jarvis_api_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "JARVIS_API_TOKEN non configurato")
    throttle.limit, throttle.lock_s = settings.auth_fail_limit, settings.auth_lock_s
    ip = client_ip(request)
    if wait := throttle.retry_after(ip):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Troppi tentativi: riprova più tardi", headers={"Retry-After": str(wait)}
        )
    supplied = creds.credentials if creds else ""
    if not secrets.compare_digest(supplied, settings.jarvis_api_token):
        throttle.fail(ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token non valido")
    throttle.ok(ip)
