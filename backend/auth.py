"""
Token-based authentication helper.
"""
import os
from passlib.context import CryptContext

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_hash = _pwd.hash(os.getenv("TOKEN", "fallback"))


def check_token(token: str) -> bool:
    """
    Compares plain token with the stored bcrypt hash.

    :param token: Plain text token from the client.
    :returns: True when token is valid.
    """
    return _pwd.verify(token, _hash)