"""Secure MongoDB configuration for APEX.

Loads local .env configuration without overriding explicitly supplied process
environment variables. The only required setting is MONGODB_URI.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv(override=False)


def get_mongodb_uri() -> str:
    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        raise RuntimeError("MONGODB_URI is not configured")
    return uri


def get_mongodb_database() -> str:
    uri = get_mongodb_uri()
    path = urlparse(uri).path.strip("/")
    return path or "benvin"
