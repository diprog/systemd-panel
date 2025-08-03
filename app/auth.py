import hmac
import hashlib
import secrets
import time


class Auth:
    """
    Stateless HMAC-based challenge auth with in-memory nonces and sessions.

    :param token_sha256_hex: Lowercase hex of SHA-256(token), stored server-side.
    :param session_ttl: Session TTL in seconds.
    """

    def __init__(self, token_sha256_hex: str, session_ttl: int):
        self._key = bytes.fromhex(token_sha256_hex)
        self._ttl = session_ttl
        self._nonces = {}   # nonce -> expiry_ts
        self._sessions = {} # sid -> expiry_ts

    def make_nonce(self) -> str:
        """
        Create a short-lived login challenge nonce.

        :returns: URL-safe base64 nonce.
        """
        nonce = secrets.token_urlsafe(24)
        self._nonces[nonce] = time.time() + 120.0
        return nonce

    def verify_login(self, nonce: str, client_hmac_hex: str) -> str | None:
        """
        Verify HMAC(nonce) computed by client with key = SHA256(token).

        :param nonce: The challenge nonce issued by the server.
        :param client_hmac_hex: Lowercase hex HMAC-SHA256 over nonce.

        :returns: Session id if success, None otherwise.
        """
        exp = self._nonces.pop(nonce, None)
        if not exp or time.time() > exp:
            return None
        expected = hmac.new(self._key, nonce.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, client_hmac_hex.lower()):
            return None
        sid = secrets.token_urlsafe(24)
        self._sessions[sid] = time.time() + self._ttl
        return sid

    def validate_sid(self, sid: str) -> bool:
        """
        Validate and extend session.

        :param sid: Session id from cookie.

        :returns: True if valid, False otherwise.
        """
        exp = self._sessions.get(sid)
        if not exp:
            return False
        if time.time() > exp:
            self._sessions.pop(sid, None)
            return False
        self._sessions[sid] = time.time() + self._ttl
        return True

    def revoke_sid(self, sid: str) -> None:
        """
        Revoke a session id.

        :param sid: Session id to revoke.

        :returns: None.
        """
        self._sessions.pop(sid, None)
