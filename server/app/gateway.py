"""Espone l'API /v1 di FreeLLMAPI (OpenAI/Anthropic-compatibile) a qualunque app, tenendo privata la sua dashboard.

Solo /v1/* viene inoltrato; l'autenticazione resta quella di FreeLLMAPI (chiave unificata `freellmapi-…`).
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from .auth import require_token
from .config import Settings, get_settings
from .llm import LLMError, read_unified_key

router = APIRouter()

# header che non vanno inoltrati da un hop all'altro (RFC 9110) e quelli che il client HTTP ricalcola
_SKIP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
         "transfer-encoding", "upgrade", "host", "content-length"}


def make_client() -> httpx.AsyncClient:
    # i completamenti in streaming possono durare minuti; la connessione locale deve invece essere immediata
    return httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=5.0))


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": {"message": message, "type": "gateway_error"}}, status_code=status)


@router.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def v1_proxy(path: str, request: Request):
    target = request.app.state.settings.freellm_internal_url
    if not target:
        raise HTTPException(404, "Gateway FreeLLMAPI non attivo")
    client: httpx.AsyncClient = request.app.state.gateway_client

    headers = {k: v for k, v in request.headers.items() if k.lower() not in _SKIP}
    upstream = client.build_request(
        request.method,
        f"{target.rstrip('/')}/v1/{path}",
        params=request.query_params,
        headers=headers,
        content=await request.body(),
    )
    try:
        resp = await client.send(upstream, stream=True)
    except httpx.ConnectError:
        return _error(503, "FreeLLMAPI si sta avviando, riprova tra qualche secondo")
    except httpx.TimeoutException:
        return _error(504, "FreeLLMAPI non ha risposto in tempo")

    out = {k: v for k, v in resp.headers.items() if k.lower() not in _SKIP}
    return StreamingResponse(resp.aiter_raw(), status_code=resp.status_code, headers=out,
                             background=BackgroundTask(resp.aclose))


@router.get("/admin/freellm", dependencies=[Depends(require_token)])
async def freellm_credentials(request: Request, settings: Settings = Depends(get_settings)) -> dict:
    """Endpoint e chiave da incollare nelle altre app. Protetto dal token personale di JARVIS."""
    if not settings.freellm_db_path:
        raise HTTPException(404, "FreeLLMAPI non è in questo container")
    try:
        key = read_unified_key(settings.freellm_db_path)
    except LLMError as e:
        raise HTTPException(503, str(e)) from e
    base = (settings.render_external_url or str(request.base_url)).rstrip("/")
    return {"base_url": f"{base}/v1", "api_key": key}
