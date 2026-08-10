"""Instancia compartida de slowapi.Limiter — vive acá (no en main.py) para que los
routers puedan importar @limiter.limit(...) sin generar un import circular con main.py."""
import os

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    limiter = Limiter(key_func=get_remote_address, default_limits=[os.getenv("RATE_LIMIT_PUBLIC", "30/minute")])
    HAS_SLOWAPI = True
except ImportError:
    class _NoopLimiter:
        def limit(self, *_args, **_kwargs):
            def decorator(func):
                return func
            return decorator

    limiter = _NoopLimiter()
    HAS_SLOWAPI = False
