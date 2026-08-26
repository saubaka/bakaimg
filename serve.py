"""Production WSGI launcher backed by the bundled Waitress server."""

from __future__ import annotations

import os

from waitress import serve

from app import create_app


def _bounded_integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise RuntimeError(f"{name}必须是整数。") from error
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name}必须在{minimum}到{maximum}之间。")
    return value


if __name__ == "__main__":
    application = create_app("production")
    host = os.getenv("CLOUDNEST_HOST", "127.0.0.1")
    trusted_hops = int(application.config["TRUST_PROXY_HOPS"])
    if trusted_hops and host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("信任转发头时生产服务必须只监听回环地址。")
    options = {
        "threads": _bounded_integer("CLOUDNEST_THREADS", 8, 2, 64),
        "ident": "Cloudnest",  # HTTP Server标识为固定契约值，不随品牌名称变化。
        "clear_untrusted_proxy_headers": not bool(trusted_hops),
    }
    options.update(
        host=host,
        port=_bounded_integer("CLOUDNEST_PORT", 5200, 1, 65535),
    )
    serve(application, **options)
