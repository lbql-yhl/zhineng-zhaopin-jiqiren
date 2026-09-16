#!/usr/bin/env python3
"""Shared Feishu OpenAPI sender with retry and clear failure details."""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_APP_ID = "cli_aa8878662d62dbee"
DEFAULT_CHAT_ID = "oc_606e61cfefd9cfb4b88409f0a480ad1d"
TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
RETRYABLE_CODES = {99991400, 99991401, 99991402, 99991403}


class FeishuSendError(RuntimeError):
    """Raised when Feishu send fails after retries."""

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail = detail or {}


def read_env_file() -> dict[str, str]:
    env_path = Path.home() / ".hermes" / ".env"
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def read_config_value(name: str, fallback: str = "") -> str:
    if os.environ.get(name):
        return os.environ[name]
    return read_env_file().get(name, fallback)


def read_secret() -> str | None:
    return read_config_value("FEISHU_APP_SECRET") or None


def network_precheck(host: str = "open.feishu.cn", port: int = 443, timeout: float = 5.0) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"ok": True, "host": host, "port": port}
    except Exception as exc:
        return {"ok": False, "host": host, "port": port, "error": f"{type(exc).__name__}: {exc}"}


def _should_retry(exc: Exception | None, response: dict[str, Any] | None) -> bool:
    if exc is not None:
        return isinstance(exc, (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError))
    if not response:
        return False
    code = response.get("code")
    return isinstance(code, int) and code in RETRYABLE_CODES


def post_json(
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    *,
    timeout: int = 20,
    retries: int = 3,
    backoff_seconds: float = 1.0,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        response: dict[str, Any] | None = None
        caught: Exception | None = None
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                response = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            response = {"code": exc.code, "msg": error_body[:1000], "http_status": exc.code}
        except Exception as exc:  # noqa: BLE001 - classified below for operational logs.
            caught = exc

        if response is not None and response.get("code", 0) == 0:
            if attempts:
                response["_retry"] = {"attempt": attempt, "previous_attempts": attempts}
            return response

        attempt_detail = {"attempt": attempt}
        if response is not None:
            attempt_detail.update({"response": response})
        if caught is not None:
            attempt_detail.update({"error": f"{type(caught).__name__}: {caught}"})
        attempts.append(attempt_detail)

        if attempt >= retries or not _should_retry(caught, response):
            detail = {"url": url, "attempts": attempts}
            if caught is not None:
                raise FeishuSendError(f"{type(caught).__name__}: {caught}", detail=detail) from caught
            raise FeishuSendError(f"Feishu API returned non-zero code: {response}", detail=detail)

        time.sleep(backoff_seconds * attempt)

    raise FeishuSendError("Feishu send failed without response", detail={"url": url, "attempts": attempts})


def get_tenant_access_token(app_id: str, app_secret: str, *, retries: int = 3, timeout: int = 20) -> str:
    data = post_json(
        TOKEN_URL,
        {"app_id": app_id, "app_secret": app_secret},
        {"Content-Type": "application/json; charset=utf-8"},
        retries=retries,
        timeout=timeout,
    )
    token = data.get("tenant_access_token")
    if not token:
        raise FeishuSendError(
            f"failed to get tenant_access_token: code={data.get('code')} msg={data.get('msg')}",
            detail={"response": data},
        )
    return str(token)


def send_post_message(
    app_id: str,
    app_secret: str,
    chat_id: str,
    title: str,
    lines: list[list[dict[str, Any]]],
    *,
    retries: int = 3,
    timeout: int = 20,
) -> dict[str, Any]:
    precheck = network_precheck(timeout=min(float(timeout), 5.0))
    if not precheck["ok"]:
        raise FeishuSendError("Feishu network precheck failed", detail={"precheck": precheck})
    token = get_tenant_access_token(app_id, app_secret, retries=retries, timeout=timeout)
    content = {"zh_cn": {"title": title, "content": lines}}
    response = post_json(
        MESSAGE_URL,
        {
            "receive_id": chat_id,
            "msg_type": "post",
            "content": json.dumps(content, ensure_ascii=False),
        },
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        retries=retries,
        timeout=timeout,
    )
    response.setdefault("_precheck", precheck)
    return response


def text_node(text: str, *, bold: bool = False) -> dict[str, Any]:
    node: dict[str, Any] = {"tag": "text", "text": text}
    if bold:
        node["style"] = ["bold"]
    return node


def is_visible_heading(line: str, *, first_nonempty: bool = False) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if first_nonempty:
        return True
    if stripped[0].isdigit() and ". " in stripped[:4]:
        return True
    return stripped.startswith("- ") and stripped.endswith("：")


def body_to_post_lines(body: str, *, bold_headings: bool = True) -> list[list[dict[str, Any]]]:
    lines: list[list[dict[str, Any]]] = []
    seen_nonempty = False
    for raw_line in body.splitlines():
        text = raw_line.rstrip()
        if not text:
            lines.append([text_node(" ")])
        else:
            first_nonempty = not seen_nonempty
            seen_nonempty = True
            lines.append([text_node(text, bold=bold_headings and is_visible_heading(text, first_nonempty=first_nonempty))])
    return lines or [[text_node("（空报告）")]]
