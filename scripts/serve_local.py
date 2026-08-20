"""Local development server.

Exists because `uvicorn.run(...)` cannot be used directly on Windows: it installs
its own event loop during startup, and psycopg's async mode refuses to run on the
ProactorEventLoop that results. The failure is not obvious — the pool times out
after ten seconds and the service reports "not fully configured", which reads like
a missing credential rather than a loop mismatch.

Driving `Server.serve()` from inside `asyncio.run` keeps the selector loop that
`app.main` selects at import. Deployment is Linux and unaffected; this file is for
development only and is not the container entrypoint.

    uv run python scripts/serve_local.py
"""

from __future__ import annotations

import asyncio
import sys

import truststore
import uvicorn

# This network intercepts TLS, and httpx ships its own trust store. Without this
# every source fetch fails with ConnectError and every claim abstains for a reason
# that has nothing to do with the evidence.
truststore.inject_into_ssl()

from app.main import create_app  # noqa: E402  (must follow the TLS injection)


async def main() -> None:
    config = uvicorn.Config(
        create_app(),
        # All interfaces, deliberately: the Android emulator reaches the host as
        # 10.0.2.2, which a loopback-only bind does not answer. Development only —
        # the container entrypoint does not use this file.
        host="0.0.0.0",  # noqa: S104
        port=8000,
        log_level="info",
        # Never "auto" here: see the module docstring.
        loop="asyncio",
    )
    await uvicorn.Server(config).serve()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
