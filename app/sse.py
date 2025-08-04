import json


async def start_sse(send) -> None:
    """
    Start a Server-Sent Events response and flush an initial chunk.

    :param send: ASGI send callable.

    :returns: None.
    """
    headers = [
        (b"content-type", b"text/event-stream; charset=utf-8"),
        (b"cache-control", b"no-cache"),
        (b"connection", b"keep-alive"),
        (b"x-accel-buffering", b"no"),
        (b"x-content-type-options", b"nosniff"),
    ]
    await send({"type": "http.response.start", "status": 200, "headers": headers})
    # Flush: a comment frame forces proxies/browsers to establish the stream
    await send({"type": "http.response.body", "body": b":ok\n\n", "more_body": True})


async def send_comment(send, text: str = "") -> None:
    """
    Send an SSE comment frame.

    :param send: ASGI send callable.
    :param text: Optional comment text.

    :returns: None.
    """
    payload = b":" + text.encode() + b"\n\n"
    await send({"type": "http.response.body", "body": payload, "more_body": True})


async def send_sse(send, data, event: str | None = None) -> None:
    """
    Send one SSE message.

    :param send: ASGI send callable.
    :param data: Any JSON-serializable payload.
    :param event: Optional event name.

    :returns: None.
    """
    payload = bytearray()
    if event:
        payload.extend(b"event: ")
        payload.extend(event.encode())
        payload.extend(b"\n")
    for line in json.dumps(data, ensure_ascii=False).splitlines():
        payload.extend(b"data: ")
        payload.extend(line.encode())
        payload.extend(b"\n")
    payload.extend(b"\n")
    await send({"type": "http.response.body", "body": bytes(payload), "more_body": True})


async def end_sse(send) -> None:
    """
    End SSE stream.

    :param send: ASGI send callable.

    :returns: None.
    """
    await send({"type": "http.response.body", "body": b"", "more_body": False})
