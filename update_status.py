#!/usr/bin/env python3
"""Update the public signal file without using accounts, cookies, or secrets."""

from __future__ import annotations

import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent if SCRIPT_DIR.name == "scripts" else SCRIPT_DIR
OUTPUT = ROOT / "status.json"
PROFILE_PROXY = "https://r.jina.ai/http://x.com/thsottiaux"
OPENAI_STATUS = "https://status.openai.com/api/v2/status.json"
X_OEMBED = "https://publish.twitter.com/oembed?omit_script=true&dnt=true&url="
TWITTER_EPOCH_MS = 1288834974657
USER_AGENT = "resetcodex-public-signal-checker/1.0"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def fetch_text(url: str, timeout: int = 25) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/plain,text/html"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def strip_html(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    return " ".join(html.unescape(" ".join(parser.parts)).split())


def tweet_time(tweet_id: str) -> datetime:
    milliseconds = (int(tweet_id) >> 22) + TWITTER_EPOCH_MS
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)


def discover_tweet_ids(markdown: str, now: datetime) -> list[str]:
    ids = re.findall(r"(?:x\.com|twitter\.com)/thsottiaux/status/(\d{15,22})", markdown, flags=re.I)
    unique: list[str] = []
    for tweet_id in ids:
        if tweet_id in unique:
            continue
        published = tweet_time(tweet_id)
        if now - timedelta(days=7) <= published <= now + timedelta(hours=1):
            unique.append(tweet_id)
    return sorted(unique, key=int, reverse=True)[:20]


def fetch_verified_tweet(tweet_id: str) -> str | None:
    direct_url = f"https://x.com/thsottiaux/status/{tweet_id}"
    payload = json.loads(fetch_text(X_OEMBED + quote(direct_url, safe="")))
    if "tibo" not in str(payload.get("author_name", "")).lower():
        return None
    return strip_html(str(payload.get("html", "")))


def classify(text: str) -> tuple[str, int, str, str] | None:
    normalized = " ".join(text.lower().split())
    about_limits = any(term in normalized for term in ("codex", "rate limit", "usage", "paid subscription"))
    if not about_limits:
        return None
    completed = any(term in normalized for term in (
        "reset has been propagated", "reset is being propagated", "full reset",
        "reset is rolling out", "reset was completed",
    ))
    upcoming = "reset" in normalized and any(term in normalized for term in (
        "will reset", "reset tomorrow", "reset later", "reset at", "reset around",
    ))
    if completed:
        return "confirmed_reset", 98, "已确认重置", "额度重置正在落地"
    if upcoming:
        return "confirmed_upcoming", 95, "已确认即将重置", "官方消息给出未来重置信号"
    if "reset" in normalized:
        return "prediction", 80, "高概率重置信号", "发现与额度重置相关的新消息"
    return None


def load_previous() -> dict:
    try:
        return json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def main() -> int:
    now = datetime.now(timezone.utc)
    previous = load_previous()
    errors: list[str] = []
    openai = {"description": "暂时无法读取", "indicator": "unknown"}
    try:
        status_payload = json.loads(fetch_text(OPENAI_STATUS))
        openai = {
            "description": status_payload.get("status", {}).get("description", "未知"),
            "indicator": status_payload.get("status", {}).get("indicator", "unknown"),
        }
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        errors.append(f"openai_status:{type(exc).__name__}")

    best: dict | None = None
    discovered = False
    try:
        profile = fetch_text(PROFILE_PROXY)
        for tweet_id in discover_tweet_ids(profile, now):
            try:
                tweet_text = fetch_verified_tweet(tweet_id)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
                continue
            if not tweet_text:
                continue
            result = classify(tweet_text)
            if not result:
                continue
            status, confidence, label, headline = result
            best = {
                "status": status,
                "label": label,
                "headline": headline,
                "confidence": confidence,
                "signal_at": tweet_time(tweet_id).isoformat().replace("+00:00", "Z"),
                "signal_id": tweet_id,
                "source_url": f"https://x.com/thsottiaux/status/{tweet_id}",
                "source_name": "Tibo（X 官方原帖）",
                "reason": "自动任务发现重置相关消息，并通过 X 官方 oEmbed 接口核验作者与原文。",
                "source_verified": True,
            }
            discovered = True
            break
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        errors.append(f"tibo_discovery:{type(exc).__name__}")

    if best is None:
        old_signal_at = previous.get("signal_at")
        try:
            old_age = now - datetime.fromisoformat(str(old_signal_at).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            old_age = timedelta(days=999)
        if previous.get("source_verified") and old_age <= timedelta(days=3):
            best = {key: previous.get(key) for key in (
                "status", "label", "headline", "confidence", "signal_at", "signal_id",
                "source_url", "source_name", "reason", "source_verified",
            )}
            best["reason"] = "本轮未发现更新；保留最近三天内、已通过 X 官方接口核验的信号。"
        else:
            best = {
                "status": "no_signal", "label": "无新信号", "headline": "等待下一次可靠消息",
                "confidence": 0, "signal_at": None, "signal_id": None,
                "source_url": "https://x.com/thsottiaux", "source_name": "Tibo（公开主页）",
                "reason": "最近三天没有发现可由官方接口核验的额度重置信号。",
                "source_verified": False,
            }

    result = {
        "schema_version": 1,
        "checked_at": now.isoformat().replace("+00:00", "Z"),
        "refresh_interval_minutes": 120,
        "discovered_new_signal": discovered,
        **best,
        "openai_status": openai,
        "source_health": "ok" if not errors else "partial",
        "errors": errors,
        "privacy": "Only public URLs were requested; no account, cookie, token, usage, chat, or device data was accessed.",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
