"""
Utility functions for the LightRAG API.
"""

import os
import argparse
import math
from typing import Optional, List, Tuple
import sys
import time
import logging
from collections import deque
from hashlib import sha256
from ascii_colors import ASCIIColors
from lightrag.api import __api_version__ as api_version
from lightrag import __version__ as core_version
from lightrag.constants import (
    DEFAULT_FORCE_LLM_SUMMARY_ON_MERGE,
)
from lightrag.api.runtime_validation import validate_runtime_target_from_env_file
from fastapi import HTTPException, Security, Request, Response, WebSocket, status
from fastapi.security import APIKeyHeader, OAuth2PasswordBearer
from starlette.status import HTTP_403_FORBIDDEN
from .auth import auth_handler
from .config import ollama_server_infos, global_args, get_env_value

logger = logging.getLogger("lightrag")

# ========== Token Renewal Rate Limiting ==========
# Cache to track last renewal time per user (username as key)
# Format: {username: last_renewal_timestamp}
_token_renewal_cache: dict[str, float] = {}
_RENEWAL_MIN_INTERVAL = 60  # Minimum 60 seconds between renewals for same user

# ========== Request Rate Limiting ==========
# Cache format: {"<scope>:<client-identity>": deque[timestamps]}
_request_rate_limit_cache: dict[str, deque[float]] = {}

# ========== Token Renewal Path Exclusions ==========
# Paths that should NOT trigger token auto-renewal
# - /health: Health check endpoint, no login required
# - /documents/paginated: Client polls this frequently (5-30s), renewal not needed
# - /documents/pipeline_status: Client polls this very frequently (2s), renewal not needed
_TOKEN_RENEWAL_SKIP_PATHS = [
    "/health",
    "/documents/paginated",
    "/documents/pipeline_status",
]


def check_env_file():
    """
    Check if .env file exists and handle user confirmation if needed.
    Returns True if should continue, False if should exit.
    """
    env_path = ".env"

    if not os.path.exists(env_path):
        warning_msg = "Warning: Startup directory must contain .env file for multi-instance support."
        ASCIIColors.yellow(warning_msg)

        # Check if running in interactive terminal
        if sys.stdin.isatty():
            response = input("Do you want to continue? (yes/no): ")
            if response.lower() != "yes":
                ASCIIColors.red("Server startup cancelled")
                return False
        return True

    is_valid, error_message = validate_runtime_target_from_env_file(env_path)
    if not is_valid:
        for line in error_message.splitlines():
            ASCIIColors.red(line)
        return False

    return True


# Get whitelist paths from global_args, only once during initialization
whitelist_paths = global_args.whitelist_paths.split(",")

# Pre-compile path matching patterns
whitelist_patterns: List[Tuple[str, bool]] = []
for path in whitelist_paths:
    path = path.strip()
    if path:
        # If path ends with /*, match all paths with that prefix
        if path.endswith("/*"):
            prefix = path[:-2]
            whitelist_patterns.append((prefix, True))  # (prefix, is_prefix_match)
        else:
            whitelist_patterns.append((path, False))  # (exact_path, is_prefix_match)


def _is_auth_configured() -> bool:
    return bool(auth_handler.accounts)


def _is_whitelisted_path(path: str) -> bool:
    for pattern, is_prefix in whitelist_patterns:
        if (is_prefix and path.startswith(pattern)) or (
            not is_prefix and path == pattern
        ):
            return True
    return False


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None

    normalized_token = token.strip()
    return normalized_token or None


def _normalize_credential(value: str | None) -> str | None:
    if value is None:
        return None

    normalized_value = value.strip()
    return normalized_value or None


def _extract_request_credentials(request: Request) -> tuple[str | None, str | None]:
    return (
        _extract_bearer_token(request.headers.get("authorization")),
        _normalize_credential(request.headers.get("x-api-key")),
    )


def _extract_websocket_credentials(
    websocket: WebSocket,
) -> tuple[str | None, str | None]:
    query_params = websocket.query_params
    token = _extract_bearer_token(websocket.headers.get("authorization"))
    if token is None:
        token = _normalize_credential(
            query_params.get("access_token") or query_params.get("token")
        )

    api_key_header_value = _normalize_credential(websocket.headers.get("x-api-key"))
    if api_key_header_value is None:
        api_key_header_value = _normalize_credential(
            query_params.get("api_key") or query_params.get("x_api_key")
        )

    return token, api_key_header_value


def _resolve_client_host(connection: Request | WebSocket) -> str:
    forwarded_for = connection.headers.get("x-forwarded-for")
    if forwarded_for:
        forwarded_client = forwarded_for.split(",", 1)[0].strip()
        if forwarded_client:
            return forwarded_client

    if connection.client and connection.client.host:
        return connection.client.host

    return "unknown"


def _credential_fingerprint(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:12]


def _resolve_rate_limit_identity(
    *,
    client_host: str,
    token: str | None,
    api_key_header_value: str | None,
) -> str:
    if token:
        try:
            token_info = auth_handler.validate_token(token)
            username = str(token_info.get("username") or "unknown")
            role = str(token_info.get("role") or "unknown")
            if role == "guest":
                return f"guest@{client_host}"
            return f"{role}:{username}@{client_host}"
        except Exception:
            return f"token:{_credential_fingerprint(token)}@{client_host}"

    if api_key_header_value:
        return f"api_key:{_credential_fingerprint(api_key_header_value)}@{client_host}"

    return f"anonymous@{client_host}"


def reset_request_rate_limit_state() -> None:
    _request_rate_limit_cache.clear()


def _enforce_rate_limit(
    *,
    rate_limit_name: str,
    identity: str,
    max_requests: int,
    window_seconds: int,
) -> None:
    if max_requests <= 0 or window_seconds <= 0:
        return

    current_time = time.time()
    cache_key = f"{rate_limit_name}:{identity}"
    request_times = _request_rate_limit_cache.setdefault(cache_key, deque())
    window_start = current_time - window_seconds

    while request_times and request_times[0] <= window_start:
        request_times.popleft()

    if len(request_times) >= max_requests:
        retry_after = max(
            1, math.ceil(window_seconds - (current_time - request_times[0]))
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    request_times.append(current_time)


def get_rate_limit_dependency(
    rate_limit_name: str,
    max_requests: int,
    window_seconds: int,
):
    async def rate_limit_dependency(request: Request):
        token, api_key_header_value = _extract_request_credentials(request)
        _enforce_rate_limit(
            rate_limit_name=rate_limit_name,
            identity=_resolve_rate_limit_identity(
                client_host=_resolve_client_host(request),
                token=token,
                api_key_header_value=api_key_header_value,
            ),
            max_requests=max_requests,
            window_seconds=window_seconds,
        )

    return rate_limit_dependency


def enforce_websocket_rate_limit(
    websocket: WebSocket,
    *,
    rate_limit_name: str,
    max_requests: int,
    window_seconds: int,
) -> None:
    token, api_key_header_value = _extract_websocket_credentials(websocket)
    _enforce_rate_limit(
        rate_limit_name=rate_limit_name,
        identity=_resolve_rate_limit_identity(
            client_host=_resolve_client_host(websocket),
            token=token,
            api_key_header_value=api_key_header_value,
        ),
        max_requests=max_requests,
        window_seconds=window_seconds,
    )


def _maybe_auto_renew_token(
    *,
    path: str,
    token_info: dict,
    response: Response | None,
) -> None:
    if response is None or not global_args.token_auto_renew:
        return

    skip_renewal = any(
        path == skip_path or path.startswith(skip_path + "/")
        for skip_path in _TOKEN_RENEWAL_SKIP_PATHS
    )

    if skip_renewal:
        logger.debug(f"Token auto-renewal skipped for path: {path}")
        return

    try:
        from datetime import datetime

        expire_time = token_info.get("exp")
        if expire_time is None:
            return

        now = datetime.utcnow()
        remaining_seconds = (expire_time - now).total_seconds()
        role = token_info.get("role", "user")
        total_hours = (
            auth_handler.guest_expire_hours
            if role == "guest"
            else auth_handler.expire_hours
        )
        total_seconds = total_hours * 3600

        if remaining_seconds >= total_seconds * global_args.token_renew_threshold:
            return

        username = token_info["username"]
        current_time = time.time()
        last_renewal = _token_renewal_cache.get(username, 0)
        time_since_last_renewal = current_time - last_renewal

        if time_since_last_renewal < _RENEWAL_MIN_INTERVAL:
            logger.debug(
                f"Token renewal skipped for {username} "
                f"(rate limit: last renewal {time_since_last_renewal:.0f}s ago)"
            )
            return

        new_token = auth_handler.create_token(
            username=username,
            role=role,
            metadata=token_info.get("metadata", {}),
        )
        response.headers["X-New-Token"] = new_token
        _token_renewal_cache[username] = current_time
        logger.info(
            f"Token auto-renewed for user {username} "
            f"(role: {role}, remaining: {remaining_seconds:.0f}s)"
        )
    except Exception as e:
        logger.warning(f"Token auto-renew failed: {e}")


def validate_auth_access(
    *,
    path: str,
    token: str | None,
    api_key_header_value: str | None,
    api_key: str | None = None,
    response: Response | None = None,
    honor_whitelist: bool = True,
) -> None:
    api_key_configured = bool(api_key)
    auth_configured = _is_auth_configured()

    if honor_whitelist and _is_whitelisted_path(path):
        return

    if token:
        token_info = auth_handler.validate_token(token)
        _maybe_auto_renew_token(path=path, token_info=token_info, response=response)

        if not auth_configured and token_info.get("role") == "guest":
            return
        if auth_configured and token_info.get("role") != "guest":
            return

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token. Please login again.",
        )

    if not auth_configured and not api_key_configured:
        return

    if (
        api_key_configured
        and api_key_header_value
        and api_key_header_value == api_key
    ):
        return

    if auth_configured and not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No credentials provided. Please login.",
        )

    if api_key_header_value:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Invalid API Key",
        )

    if api_key_configured and not api_key_header_value:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="API Key required",
        )

    raise HTTPException(
        status_code=HTTP_403_FORBIDDEN,
        detail="API Key required or login authentication required.",
    )


def get_combined_auth_dependency(api_key: Optional[str] = None):
    """
    Create a combined authentication dependency that implements authentication logic
    based on API key, OAuth2 token, and whitelist paths.

    Args:
        api_key (Optional[str]): API key for validation

    Returns:
        Callable: A dependency function that implements the authentication logic
    """
    # Create security dependencies with proper descriptions for Swagger UI
    oauth2_scheme = OAuth2PasswordBearer(
        tokenUrl="login", auto_error=False, description="OAuth2 Password Authentication"
    )

    # If API key is configured, create an API key header security
    api_key_header = None
    if api_key:
        api_key_header = APIKeyHeader(
            name="X-API-Key", auto_error=False, description="API Key Authentication"
        )

    async def combined_dependency(
        request: Request,
        response: Response,  # Added: needed to return new token via response header
        token: str = Security(oauth2_scheme),
        api_key_header_value: Optional[str] = None
        if api_key_header is None
        else Security(api_key_header),
    ):
        validate_auth_access(
            path=request.url.path,
            token=token,
            api_key_header_value=api_key_header_value,
            api_key=api_key,
            response=response,
            honor_whitelist=True,
        )

    return combined_dependency


def get_strict_auth_dependency(api_key: Optional[str] = None):
    oauth2_scheme = OAuth2PasswordBearer(
        tokenUrl="login", auto_error=False, description="OAuth2 Password Authentication"
    )

    api_key_header = None
    if api_key:
        api_key_header = APIKeyHeader(
            name="X-API-Key", auto_error=False, description="API Key Authentication"
        )

    async def strict_dependency(
        request: Request,
        response: Response,
        token: str = Security(oauth2_scheme),
        api_key_header_value: Optional[str] = None
        if api_key_header is None
        else Security(api_key_header),
    ):
        validate_auth_access(
            path=request.url.path,
            token=token,
            api_key_header_value=api_key_header_value,
            api_key=api_key,
            response=response,
            honor_whitelist=False,
        )

    return strict_dependency


def authorize_websocket(
    websocket: WebSocket,
    *,
    api_key: Optional[str] = None,
    honor_whitelist: bool = True,
) -> None:
    token, api_key_header_value = _extract_websocket_credentials(websocket)

    validate_auth_access(
        path=websocket.url.path,
        token=token,
        api_key_header_value=api_key_header_value,
        api_key=api_key,
        response=None,
        honor_whitelist=honor_whitelist,
    )


def display_splash_screen(args: argparse.Namespace) -> None:
    """
    Display a colorful splash screen showing LightRAG server configuration

    Args:
        args: Parsed command line arguments
    """
    # Banner
    # Banner
    top_border = "╔══════════════════════════════════════════════════════════════╗"
    bottom_border = "╚══════════════════════════════════════════════════════════════╝"
    width = len(top_border) - 4  # width inside the borders

    line1_text = f"LightRAG Server v{core_version}/{api_version}"
    line2_text = "Fast, Lightweight RAG Server Implementation"

    line1 = f"║ {line1_text.center(width)} ║"
    line2 = f"║ {line2_text.center(width)} ║"

    banner = f"""
    {top_border}
    {line1}
    {line2}
    {bottom_border}
    """
    ASCIIColors.cyan(banner)

    # Server Configuration
    ASCIIColors.magenta("\n📡 Server Configuration:")
    ASCIIColors.white("    ├─ Host: ", end="")
    ASCIIColors.yellow(f"{args.host}")
    ASCIIColors.white("    ├─ Port: ", end="")
    ASCIIColors.yellow(f"{args.port}")
    ASCIIColors.white("    ├─ Workers: ", end="")
    ASCIIColors.yellow(f"{args.workers}")
    ASCIIColors.white("    ├─ Timeout: ", end="")
    ASCIIColors.yellow(f"{args.timeout}")
    ASCIIColors.white("    ├─ CORS Origins: ", end="")
    ASCIIColors.yellow(f"{args.cors_origins}")
    ASCIIColors.white("    ├─ SSL Enabled: ", end="")
    ASCIIColors.yellow(f"{args.ssl}")
    if args.ssl:
        ASCIIColors.white("    ├─ SSL Cert: ", end="")
        ASCIIColors.yellow(f"{args.ssl_certfile}")
        ASCIIColors.white("    ├─ SSL Key: ", end="")
        ASCIIColors.yellow(f"{args.ssl_keyfile}")
    ASCIIColors.white("    ├─ Ollama Emulating Model: ", end="")
    ASCIIColors.yellow(f"{ollama_server_infos.LIGHTRAG_MODEL}")
    ASCIIColors.white("    ├─ Log Level: ", end="")
    ASCIIColors.yellow(f"{args.log_level}")
    ASCIIColors.white("    ├─ Verbose Debug: ", end="")
    ASCIIColors.yellow(f"{args.verbose}")
    ASCIIColors.white("    ├─ API Key: ", end="")
    ASCIIColors.yellow("Set" if args.key else "Not Set")
    ASCIIColors.white("    └─ JWT Auth: ", end="")
    ASCIIColors.yellow("Enabled" if args.auth_accounts else "Disabled")

    # Directory Configuration
    ASCIIColors.magenta("\n📂 Directory Configuration:")
    ASCIIColors.white("    ├─ Working Directory: ", end="")
    ASCIIColors.yellow(f"{args.working_dir}")
    ASCIIColors.white("    └─ Input Directory: ", end="")
    ASCIIColors.yellow(f"{args.input_dir}")

    # LLM Configuration
    ASCIIColors.magenta("\n🤖 LLM Configuration:")
    ASCIIColors.white("    ├─ Binding: ", end="")
    ASCIIColors.yellow(f"{args.llm_binding}")
    ASCIIColors.white("    ├─ Host: ", end="")
    ASCIIColors.yellow(f"{args.llm_binding_host}")
    ASCIIColors.white("    ├─ Model: ", end="")
    ASCIIColors.yellow(f"{args.llm_model}")
    ASCIIColors.white("    ├─ Max Async for LLM: ", end="")
    ASCIIColors.yellow(f"{args.max_async}")
    ASCIIColors.white("    ├─ Summary Context Size: ", end="")
    ASCIIColors.yellow(f"{args.summary_context_size}")
    ASCIIColors.white("    ├─ LLM Cache Enabled: ", end="")
    ASCIIColors.yellow(f"{args.enable_llm_cache}")
    ASCIIColors.white("    └─ LLM Cache for Extraction Enabled: ", end="")
    ASCIIColors.yellow(f"{args.enable_llm_cache_for_extract}")

    # Embedding Configuration
    ASCIIColors.magenta("\n📊 Embedding Configuration:")
    ASCIIColors.white("    ├─ Binding: ", end="")
    ASCIIColors.yellow(f"{args.embedding_binding}")
    ASCIIColors.white("    ├─ Host: ", end="")
    ASCIIColors.yellow(f"{args.embedding_binding_host}")
    ASCIIColors.white("    ├─ Model: ", end="")
    ASCIIColors.yellow(f"{args.embedding_model}")
    ASCIIColors.white("    └─ Dimensions: ", end="")
    ASCIIColors.yellow(f"{args.embedding_dim}")

    # RAG Configuration
    ASCIIColors.magenta("\n⚙️ RAG Configuration:")
    ASCIIColors.white("    ├─ Summary Language: ", end="")
    ASCIIColors.yellow(f"{args.summary_language}")
    ASCIIColors.white("    ├─ Entity Types: ", end="")
    ASCIIColors.yellow(f"{args.entity_types}")
    ASCIIColors.white("    ├─ Max Parallel Insert: ", end="")
    ASCIIColors.yellow(f"{args.max_parallel_insert}")
    ASCIIColors.white("    ├─ Chunk Size: ", end="")
    ASCIIColors.yellow(f"{args.chunk_size}")
    ASCIIColors.white("    ├─ Chunk Overlap Size: ", end="")
    ASCIIColors.yellow(f"{args.chunk_overlap_size}")
    ASCIIColors.white("    ├─ Cosine Threshold: ", end="")
    ASCIIColors.yellow(f"{args.cosine_threshold}")
    ASCIIColors.white("    ├─ Top-K: ", end="")
    ASCIIColors.yellow(f"{args.top_k}")
    ASCIIColors.white("    └─ Force LLM Summary on Merge: ", end="")
    ASCIIColors.yellow(
        f"{get_env_value('FORCE_LLM_SUMMARY_ON_MERGE', DEFAULT_FORCE_LLM_SUMMARY_ON_MERGE, int)}"
    )

    # System Configuration
    ASCIIColors.magenta("\n💾 Storage Configuration:")
    ASCIIColors.white("    ├─ KV Storage: ", end="")
    ASCIIColors.yellow(f"{args.kv_storage}")
    ASCIIColors.white("    ├─ Vector Storage: ", end="")
    ASCIIColors.yellow(f"{args.vector_storage}")
    ASCIIColors.white("    ├─ Graph Storage: ", end="")
    ASCIIColors.yellow(f"{args.graph_storage}")
    ASCIIColors.white("    ├─ Document Status Storage: ", end="")
    ASCIIColors.yellow(f"{args.doc_status_storage}")
    ASCIIColors.white("    └─ Workspace: ", end="")
    ASCIIColors.yellow(f"{args.workspace if args.workspace else '-'}")

    # Server Status
    ASCIIColors.green("\n✨ Server starting up...\n")

    # Server Access Information
    protocol = "https" if args.ssl else "http"
    if args.host == "0.0.0.0":
        ASCIIColors.magenta("\n🌐 Server Access Information:")
        ASCIIColors.white("    ├─ WebUI (local): ", end="")
        ASCIIColors.yellow(f"{protocol}://localhost:{args.port}")
        ASCIIColors.white("    ├─ Remote Access: ", end="")
        ASCIIColors.yellow(f"{protocol}://<your-ip-address>:{args.port}")
        ASCIIColors.white("    ├─ API Documentation (local): ", end="")
        ASCIIColors.yellow(f"{protocol}://localhost:{args.port}/docs")
        ASCIIColors.white("    └─ Alternative Documentation (local): ", end="")
        ASCIIColors.yellow(f"{protocol}://localhost:{args.port}/redoc")

        ASCIIColors.magenta("\n📝 Note:")
        ASCIIColors.cyan("""    Since the server is running on 0.0.0.0:
    - Use 'localhost' or '127.0.0.1' for local access
    - Use your machine's IP address for remote access
    - To find your IP address:
      • Windows: Run 'ipconfig' in terminal
      • Linux/Mac: Run 'ifconfig' or 'ip addr' in terminal
    """)
    else:
        base_url = f"{protocol}://{args.host}:{args.port}"
        ASCIIColors.magenta("\n🌐 Server Access Information:")
        ASCIIColors.white("    ├─ WebUI (local): ", end="")
        ASCIIColors.yellow(f"{base_url}")
        ASCIIColors.white("    ├─ API Documentation: ", end="")
        ASCIIColors.yellow(f"{base_url}/docs")
        ASCIIColors.white("    └─ Alternative Documentation: ", end="")
        ASCIIColors.yellow(f"{base_url}/redoc")

    # Security Notice
    if args.key:
        ASCIIColors.yellow("\n⚠️  Security Notice:")
        ASCIIColors.white("""    API Key authentication is enabled.
    Make sure to include the X-API-Key header in all your requests.
    """)
    if args.auth_accounts:
        ASCIIColors.yellow("\n⚠️  Security Notice:")
        ASCIIColors.white("""    JWT authentication is enabled.
    Make sure to login before making the request, and include the 'Authorization' in the header.
    """)

    # Ensure splash output flush to system log
    sys.stdout.flush()
