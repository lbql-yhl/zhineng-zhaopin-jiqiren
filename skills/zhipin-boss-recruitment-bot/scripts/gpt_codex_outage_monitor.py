#!/usr/bin/env python3
"""Monitor GPT/Codex availability and send Feishu alerts without GPT."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from feishu_gateway import DEFAULT_APP_ID, DEFAULT_CHAT_ID, FeishuSendError, send_post_message  # noqa: E402

YE_HAILIN_OPEN_ID = "ou_be28de7519471294e523a2708caa6190"
DEFAULT_STATE_PATH = Path.home() / ".hermes" / "state" / "xiaozhao_gpt_codex_monitor.json"
DEFAULT_LOG_PATH = Path.home() / ".hermes" / "logs" / "xiaozhao_gpt_codex_monitor.log"
CHATGPT_CODEX_PROBE_URL = "https://chatgpt.com/backend-api/codex"


def now() -> datetime:
    return datetime.now().astimezone()


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def append_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


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


def post_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout: int = 20) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {error_body}") from exc


def get_feishu_token(app_id: str, app_secret: str) -> str:
    data = post_json(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
        {"Content-Type": "application/json; charset=utf-8"},
    )
    token = data.get("tenant_access_token")
    if not token:
        raise RuntimeError(f"failed to get tenant_access_token: code={data.get('code')} msg={data.get('msg')}")
    return str(token)


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def check_tcp(host: str, port: int, timeout: int) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "ok"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def check_http_reachable(url: str, timeout: int) -> tuple[bool, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "xiaozhao-gpt-codex-monitor/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"http_{resp.status}"
    except urllib.error.HTTPError as exc:
        if exc.code in {401, 403, 404, 405, 429}:
            return True, f"http_{exc.code}"
        return False, f"http_{exc.code}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def check_command(command: str, timeout: int) -> tuple[bool, str]:
    path = shutil.which(command)
    if not path:
        return False, "missing"
    try:
        result = subprocess.run(
            [path, "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if result.returncode == 0:
        version = (result.stdout or result.stderr).strip().splitlines()
        return True, version[0][:80] if version else "ok"
    return False, f"exit_{result.returncode}: {(result.stderr or result.stdout).strip()[:120]}"


def check_required_files() -> tuple[bool, str]:
    paths = {
        "codex_auth": Path.home() / ".codex" / "auth.json",
        "codex_config": Path.home() / ".codex" / "config.toml",
        "hermes_config": Path.home() / ".hermes" / "config.yaml",
    }
    missing = [name for name, path in paths.items() if not path.exists()]
    if missing:
        return False, "missing=" + ",".join(missing)
    return True, "ok"


def run_checks(timeout: int) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    for name, fn in {
        "openai_tcp": lambda: check_tcp("chatgpt.com", 443, timeout),
        "feishu_tcp": lambda: check_tcp("open.feishu.cn", 443, timeout),
        "codex_backend": lambda: check_http_reachable(CHATGPT_CODEX_PROBE_URL, timeout),
        "codex_cli": lambda: check_command("codex", timeout),
        "required_files": check_required_files,
    }.items():
        ok, detail = fn()
        checks[name] = {"ok": ok, "detail": detail}

    codex_app_exists = Path("/Applications/Codex.app").exists()
    checks["codex_app"] = {"ok": codex_app_exists, "detail": "ok" if codex_app_exists else "missing"}

    openai_path_ok = checks["codex_backend"]["ok"] or checks["openai_tcp"]["ok"]
    codex_local_ok = checks["codex_cli"]["ok"] or checks["codex_app"]["ok"]
    required_files_ok = checks["required_files"]["ok"]
    failed: list[str] = []
    if not openai_path_ok:
        failed.append("openai_codex_path")
    if not codex_local_ok:
        failed.append("codex_local")
    if not required_files_ok:
        failed.append("required_files")
    warnings = [name for name, item in checks.items() if not item["ok"] and name not in {"codex_cli", "codex_app"}]
    status = "ok" if not failed else "failed"
    return {"status": status, "failed": failed, "warnings": warnings, "checks": checks}


def build_alert_lines(result: dict[str, Any], consecutive_failures: int, created_at: str) -> list[list[dict[str, str]]]:
    failed = "、".join(result["failed"]) or "未知"
    detail_parts = []
    if "openai_codex_path" in result["failed"]:
        detail_parts.append(
            "openai_tcp="
            + result["checks"]["openai_tcp"]["detail"]
            + "；codex_backend="
            + result["checks"]["codex_backend"]["detail"]
        )
    if "codex_local" in result["failed"]:
        detail_parts.append(
            "codex_cli=" + result["checks"]["codex_cli"]["detail"] + "；codex_app=" + result["checks"]["codex_app"]["detail"]
        )
    if "required_files" in result["failed"]:
        detail_parts.append("required_files=" + result["checks"]["required_files"]["detail"])
    if result.get("warnings"):
        warning_text = "、".join(str(item) for item in result["warnings"])
        detail_parts.append(f"warning={warning_text}")
    detail = "；".join(detail_parts)[:900] if detail_parts else "无"
    return [
        [
            {"tag": "at", "user_id": YE_HAILIN_OPEN_ID, "user_name": "叶海淋"},
            {"tag": "text", "text": " 小昭风险提醒：GPT/Codex 监控发现异常"},
        ],
        [{"tag": "text", "text": f"时间：{created_at}"}],
        [{"tag": "text", "text": f"连续失败：{consecutive_failures} 次"}],
        [{"tag": "text", "text": f"失败项目：{failed}"}],
        [{"tag": "text", "text": f"检查详情：{detail}"}],
        [{"tag": "text", "text": "处理建议：请先检查网络和 Codex；恢复前不要启动 BOSS 自动筛选。"}],
    ]


def send_alert(args: argparse.Namespace, result: dict[str, Any], consecutive_failures: int, created_at: str) -> dict[str, Any]:
    if args.dry_run:
        return {"dry_run": True}
    app_secret = read_config_value("FEISHU_APP_SECRET")
    if not app_secret:
        return {"code": -1, "error": "FEISHU_APP_SECRET missing"}
    app_id = args.feishu_app_id or read_config_value("FEISHU_APP_ID", DEFAULT_APP_ID)
    chat_id = args.feishu_chat_id or read_config_value("FEISHU_CHAT_ID", DEFAULT_CHAT_ID)
    try:
        return send_post_message(
            app_id,
            app_secret,
            chat_id,
            "小昭 GPT/Codex 风险提醒",
            build_alert_lines(result, consecutive_failures, created_at),
        )
    except FeishuSendError as exc:
        return {"code": -1, "error": str(exc), "detail": exc.detail}


def should_alert(state: dict[str, Any], args: argparse.Namespace, consecutive_failures: int) -> bool:
    if consecutive_failures < args.threshold:
        return False
    last_alert = parse_dt(state.get("last_alert_at"))
    if not last_alert:
        return True
    return now() - last_alert >= timedelta(minutes=args.cooldown_minutes)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=int, default=2, help="Consecutive failures before alerting.")
    parser.add_argument("--cooldown-minutes", type=int, default=60, help="Minimum minutes between alerts.")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH))
    parser.add_argument("--feishu-app-id", default="")
    parser.add_argument("--feishu-chat-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    created_at = now_iso()
    state_path = Path(args.state_path)
    log_path = Path(args.log_path)
    state = load_state(state_path)
    result = run_checks(args.timeout)

    if result["status"] == "ok":
        state["consecutive_failures"] = 0
        state["last_ok_at"] = created_at
        state["last_status"] = "ok"
        alert_response: dict[str, Any] | None = None
    else:
        state["consecutive_failures"] = int(state.get("consecutive_failures") or 0) + 1
        state["last_failed_at"] = created_at
        state["last_status"] = "failed"
        if should_alert(state, args, state["consecutive_failures"]):
            alert_response = send_alert(args, result, state["consecutive_failures"], created_at)
            state["last_alert_at"] = created_at
            state["last_alert_response_code"] = alert_response.get("code")
        else:
            alert_response = None

    state["updated_at"] = created_at
    state["last_result"] = result
    save_state(state_path, state)
    output = {
        "time": created_at,
        "status": result["status"],
        "failed": result["failed"],
        "warnings": result.get("warnings", []),
        "consecutive_failures": state.get("consecutive_failures", 0),
        "alert_response": alert_response,
    }
    append_log(log_path, output)
    print(json.dumps(output, ensure_ascii=False))
    if result["status"] != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
