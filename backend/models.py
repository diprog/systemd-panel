"""
Pydantic models used in the API.
"""

from pydantic import BaseModel


class ServiceStatus(BaseModel):
    name: str
    active: bool
    sub: str