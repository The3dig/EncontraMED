"""Cliente HTTP compartilhado (identificação honesta, timeouts, classificação de erros)."""
from __future__ import annotations

import httpx

from .config import settings


def make_client(transport: httpx.AsyncBaseTransport | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(settings.http_timeout),
        headers={"User-Agent": settings.user_agent, "Accept": "application/json",
                 "Accept-Language": "pt-BR,pt;q=0.9"},
        follow_redirects=True,
        transport=transport,
        limits=httpx.Limits(max_connections=settings.max_concurrency * 2),
    )


def classify_error(exc: Exception) -> tuple[str, str]:
    """-> (status, mensagem) para o relatório de fontes."""
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403, 429):
            return "bloqueado", f"HTTP {code}: a fonte recusou a consulta automatizada (bloqueio/limite)."
        if code == 404:
            return "erro", "HTTP 404: endpoint não encontrado (a fonte pode ter mudado de plataforma)."
        return "erro", f"HTTP {code}"
    if isinstance(exc, httpx.ProxyError):
        return "bloqueado", f"Rede/proxy bloqueou o acesso: {exc}"
    if isinstance(exc, httpx.TimeoutException):
        return "erro", "Tempo esgotado ao consultar a fonte."
    if isinstance(exc, httpx.HTTPError):
        return "erro", f"Falha de rede: {exc.__class__.__name__}: {exc}"
    return "erro", f"{exc.__class__.__name__}: {exc}"
