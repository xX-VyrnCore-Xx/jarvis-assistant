import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)


def require_token(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.jarvis_api_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "JARVIS_API_TOKEN non configurato")
    supplied = creds.credentials if creds else ""
    if not secrets.compare_digest(supplied, settings.jarvis_api_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token non valido")
