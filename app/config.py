import os

from dotenv import load_dotenv

# Load .env file if present
load_dotenv()


def _is_hex(s):
    try:
        int(s, 16)
        return True
    except Exception:
        return False


class Config:
    """
    Runtime configuration loaded from environment variables.

    :param token_sha256: Hex-encoded SHA-256 of the login token.
    :param cookie_secure: Whether to set the session cookie as Secure.
    :param session_ttl: Session time-to-live in seconds.
    :param service_dir: Directory to scan for .service units.
    :param bind: Host to bind the HTTP server on.
    :param port: Port to listen on.
    """

    def __init__(self):
        self.token_sha256 = os.environ.get("AUTH_TOKEN_SHA256", "").strip().lower()
        if len(self.token_sha256) != 64 or not _is_hex(self.token_sha256):
            raise RuntimeError("AUTH_TOKEN_SHA256 must be a 64-char lowercase hex string (SHA-256).")
        self.cookie_secure = os.environ.get("COOKIE_SECURE", "0") in ("1", "true", "yes", "on")
        self.session_ttl = int(os.environ.get("SESSION_TTL_SECONDS", "86400"))
        self.service_dir = os.environ.get("SYSTEMD_SERVICE_DIR", "/etc/systemd/system")
        self.bind = os.environ.get("BIND", "0.0.0.0")
        self.port = int(os.environ.get("PORT", "8080"))


CONFIG = Config()
