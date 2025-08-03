import json
from urllib.parse import parse_qs


def lower_headers(scope) -> dict:
    """
    Convert ASGI headers to a lowercase dict.

    :param scope: ASGI scope.

    :returns: Dict of headers in lowercase.
    """
    headers = {}
    for k, v in scope["headers"]:
        headers[k.decode().lower()] = v.decode()
    return headers


async def read_body(receive) -> bytes:
    """
    Read full HTTP request body (possibly chunked).

    :param receive: ASGI receive callable.

    :returns: Raw request body bytes.
    """
    body = bytearray()
    more = True
    while more:
        event = await receive()
        if event["type"] != "http.request":
            break
        data = event.get("body", b"")
        if data:
            body.extend(data)
        more = event.get("more_body", False)
    return bytes(body)


async def read_json(receive) -> dict:
    """
    Parse JSON body.

    :param receive: ASGI receive callable.

    :returns: Parsed JSON dict (or empty dict).
    """
    data = await read_body(receive)
    if not data:
        return {}
    return json.loads(data.decode())


def get_cookies(headers: dict) -> dict:
    """
    Parse Cookie header.

    :param headers: Lowercase headers.

    :returns: Dict of cookie name->value.
    """
    cookie = headers.get("cookie", "")
    result = {}
    for part in cookie.split(";"):
        if "=" in part:
            name, value = part.split("=", 1)
            result[name.strip()] = value.strip()
    return result


async def send_json(send, status: int, obj, extra_headers: list | None = None) -> None:
    """
    Send JSON response.

    :param send: ASGI send callable.
    :param status: HTTP status code.
    :param obj: JSON-serializable body.
    :param extra_headers: Optional list of (key, value) headers.

    :returns: None.
    """
    payload = json.dumps(obj, ensure_ascii=False).encode()
    headers = [
        (b"content-type", b"application/json; charset=utf-8"),
        (b"content-length", str(len(payload)).encode()),
        (b"cache-control", b"no-store"),
        (b"x-content-type-options", b"nosniff"),
        (b"referrer-policy", b"no-referrer"),
    ]
    if extra_headers:
        headers += [
            ((k if isinstance(k, bytes) else k.encode()), (v if isinstance(v, bytes) else v.encode()))
            for k, v in extra_headers
        ]
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": payload})


def query_params(scope) -> dict:
    """
    Parse query string.

    :param scope: ASGI scope.

    :returns: Dict of query params (first values).
    """
    raw = scope.get("query_string", b"").decode()
    return {k: v[0] for k, v in parse_qs(raw).items()}
