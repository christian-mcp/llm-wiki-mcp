"""Slack channel history import for wiki raw sources."""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

from . import config as cfg
from . import ingest_raw
from . import slugify

SLACK_API_BASE = "https://slack.com/api"
DEFAULT_CHANNELS = (
    "academic-research",
    "quant-research",
    "ai",
    "risk",
    "markets",
)

_CHANNEL_ID_RE = re.compile(r"^[CGD][A-Z0-9]+$")
_ANGLE_TOKEN_RE = re.compile(r"<([^<>]+)>")
_MENTION_RE = re.compile(r"<@([A-Z0-9]+)>")


class SlackIngestError(Exception):
    """Raised when Slack import cannot continue."""


@dataclass
class SlackChannel:
    id: str
    name: str


@dataclass
class SlackMessage:
    ts: str
    text: str
    user_id: str | None = None
    author: str = "unknown"
    subtype: str | None = None
    thread_ts: str | None = None
    is_thread_reply: bool = False
    files: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SlackFetchOutcome:
    channel: str
    channel_id: str
    result: str
    relpath: str = ""
    source_id: int | None = None
    message_count: int = 0
    message: str = ""


class SlackClient:
    """Small Slack Web API client that keeps tokens out of command arguments."""

    def __init__(self, token: str, *, timeout: float = 30.0) -> None:
        self.token = token
        self._client = httpx.Client(
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
        )
        self._user_cache: dict[str, str] = {}
        self._user_lookup_disabled = False

    def close(self) -> None:
        self._client.close()

    def api_get(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        url = f"{SLACK_API_BASE}/{method}"
        request_params = dict(params)
        for attempt in range(3):
            try:
                response = self._client.get(url, params=request_params)
            except httpx.HTTPError as e:
                raise SlackIngestError(f"{method} request failed: {e}") from e
            if response.status_code == 429 and attempt < 2:
                retry_after = int(response.headers.get("Retry-After", "30"))
                time.sleep(max(retry_after, 1))
                continue
            try:
                response.raise_for_status()
                data = response.json()
            except (httpx.HTTPError, ValueError) as e:
                raise SlackIngestError(f"{method} response failed: {e}") from e
            if data.get("ok"):
                return data
            if (
                data.get("error") == "invalid_limit"
                and int(request_params.get("limit") or 0) > 15
            ):
                request_params["limit"] = 15
                continue
            raise SlackIngestError(f"{method} failed: {data.get('error', 'unknown_error')}")
        raise SlackIngestError(f"{method} failed: Slack rate limit did not clear")

    def resolve_user_name(self, user_id: str | None) -> str:
        if not user_id:
            return "unknown"
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        if self._user_lookup_disabled:
            return user_id

        try:
            data = self.api_get("users.info", {"user": user_id})
        except SlackIngestError as e:
            if "missing_scope" in str(e):
                self._user_lookup_disabled = True
            return user_id

        user = data.get("user") or {}
        profile = user.get("profile") or {}
        name = (
            profile.get("display_name")
            or profile.get("real_name")
            or user.get("real_name")
            or user.get("name")
            or user_id
        )
        self._user_cache[user_id] = name
        return name


def _clean_channel_name(channel: str) -> str:
    channel = channel.strip()
    if channel.startswith("#"):
        channel = channel[1:]
    return channel


def resolve_channels(client: SlackClient, channels: list[str]) -> list[SlackChannel]:
    """Resolve channel names or IDs into Slack conversation IDs."""
    cleaned = [_clean_channel_name(channel) for channel in channels if channel.strip()]
    ids = [item for item in cleaned if _CHANNEL_ID_RE.match(item)]
    names = [item for item in cleaned if item not in ids]

    resolved: list[SlackChannel] = []
    for channel_id in ids:
        name = channel_id
        try:
            data = client.api_get("conversations.info", {"channel": channel_id})
            channel = data.get("channel") or {}
            name = channel.get("name") or channel.get("name_normalized") or channel_id
        except SlackIngestError:
            pass
        resolved.append(SlackChannel(id=channel_id, name=name))

    if not names:
        return resolved

    by_name: dict[str, SlackChannel] = {}
    cursor = ""
    while True:
        data = client.api_get(
            "conversations.list",
            {
                "types": "public_channel,private_channel",
                "exclude_archived": "true",
                "limit": 200,
                **({"cursor": cursor} if cursor else {}),
            },
        )
        for raw in data.get("channels", []):
            name = raw.get("name_normalized") or raw.get("name")
            channel_id = raw.get("id")
            if name and channel_id:
                by_name[name] = SlackChannel(id=channel_id, name=name)
        cursor = ((data.get("response_metadata") or {}).get("next_cursor") or "").strip()
        if not cursor:
            break

    missing = [name for name in names if name not in by_name]
    if missing:
        raise SlackIngestError(
            "Could not resolve Slack channel(s): "
            + ", ".join(f"#{name}" for name in missing)
            + ". Make sure the bot has channels:read/groups:read and can see them."
        )

    resolved.extend(by_name[name] for name in names)
    return resolved


def fetch_messages(
    client: SlackClient,
    channel_id: str,
    *,
    oldest: float,
    latest: float,
    limit: int = 200,
    include_threads: bool = True,
) -> list[SlackMessage]:
    """Fetch channel messages in a time window, optionally including replies."""
    raw_messages: list[dict[str, Any]] = []
    cursor = ""
    while True:
        data = client.api_get(
            "conversations.history",
            {
                "channel": channel_id,
                "oldest": f"{oldest:.6f}",
                "latest": f"{latest:.6f}",
                "inclusive": "true",
                "limit": limit,
                **({"cursor": cursor} if cursor else {}),
            },
        )
        raw_messages.extend(data.get("messages", []))
        cursor = ((data.get("response_metadata") or {}).get("next_cursor") or "").strip()
        if not cursor:
            break

    messages: list[SlackMessage] = []
    seen_ts: set[str] = set()
    for raw in sorted(raw_messages, key=lambda item: float(item.get("ts", 0))):
        msg = _message_from_raw(client, raw)
        if msg and msg.ts not in seen_ts:
            messages.append(msg)
            seen_ts.add(msg.ts)

        if include_threads and raw.get("reply_count") and raw.get("thread_ts"):
            replies = fetch_thread_replies(
                client,
                channel_id,
                thread_ts=raw["thread_ts"],
                oldest=oldest,
                latest=latest,
                limit=limit,
            )
            for reply in replies:
                if reply.ts not in seen_ts:
                    messages.append(reply)
                    seen_ts.add(reply.ts)

    return sorted(
        messages,
        key=lambda item: (
            float(item.thread_ts or item.ts),
            1 if item.is_thread_reply else 0,
            float(item.ts),
        ),
    )


def fetch_thread_replies(
    client: SlackClient,
    channel_id: str,
    *,
    thread_ts: str,
    oldest: float,
    latest: float,
    limit: int = 200,
) -> list[SlackMessage]:
    replies: list[SlackMessage] = []
    cursor = ""
    while True:
        data = client.api_get(
            "conversations.replies",
            {
                "channel": channel_id,
                "ts": thread_ts,
                "oldest": f"{oldest:.6f}",
                "latest": f"{latest:.6f}",
                "inclusive": "true",
                "limit": limit,
                **({"cursor": cursor} if cursor else {}),
            },
        )
        for raw in data.get("messages", []):
            if raw.get("ts") == thread_ts:
                continue
            msg = _message_from_raw(client, raw, is_thread_reply=True)
            if msg:
                replies.append(msg)
        cursor = ((data.get("response_metadata") or {}).get("next_cursor") or "").strip()
        if not cursor:
            break
    return sorted(replies, key=lambda item: float(item.ts))


def _message_from_raw(
    client: SlackClient,
    raw: dict[str, Any],
    *,
    is_thread_reply: bool = False,
) -> SlackMessage | None:
    text = str(raw.get("text") or "").strip()
    files = raw.get("files") or []
    if not text and not files:
        return None

    user_id = raw.get("user") or raw.get("bot_id")
    author = (
        raw.get("username")
        or (raw.get("bot_profile") or {}).get("name")
        or client.resolve_user_name(user_id)
    )

    return SlackMessage(
        ts=str(raw.get("ts") or ""),
        text=text,
        user_id=user_id,
        author=author,
        subtype=raw.get("subtype"),
        thread_ts=raw.get("thread_ts"),
        is_thread_reply=is_thread_reply,
        files=files if isinstance(files, list) else [],
    )


def _format_ts(ts: str) -> tuple[str, str]:
    dt = datetime.fromtimestamp(float(ts), timezone.utc)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M UTC")


def _clean_slack_text(text: str, user_names: dict[str, str]) -> str:
    text = html.unescape(text)

    def replace_angle(match: re.Match[str]) -> str:
        token = match.group(1)
        if token.startswith("@"):
            user_id = token[1:]
            return f"@{user_names.get(user_id, user_id)}"
        if token.startswith("#"):
            parts = token.split("|", 1)
            return f"#{parts[1]}" if len(parts) == 2 else token
        if token.startswith("!"):
            return f"@{token[1:]}"
        if "|" in token:
            url, label = token.split("|", 1)
            if url.startswith(("http://", "https://")):
                return f"[{label}]({url})"
            return label
        return token

    return _ANGLE_TOKEN_RE.sub(replace_angle, text).strip()


def _file_lines(files: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for file_obj in files:
        title = file_obj.get("title") or file_obj.get("name") or "file"
        permalink = file_obj.get("permalink") or file_obj.get("url_private")
        if permalink:
            lines.append(f"  - File: [{title}]({permalink})")
        else:
            lines.append(f"  - File: {title}")
    return lines


def render_digest(
    channel: SlackChannel,
    messages: list[SlackMessage],
    *,
    oldest_dt: datetime,
    latest_dt: datetime,
    lookback_days: int,
) -> str:
    """Render Slack history as a stable, citation-friendly markdown source."""
    user_names = {
        match.group(1): message.author
        for message in messages
        for match in _MENTION_RE.finditer(message.text)
    }
    for message in messages:
        if message.user_id:
            user_names.setdefault(message.user_id, message.author)

    title = f"Slack digest: #{channel.name} last {lookback_days} days"
    frontmatter = {
        "title": title,
        "type": "slack-digest",
        "channel": channel.name,
        "channel_id": channel.id,
        "lookback_days": lookback_days,
        "oldest": oldest_dt.isoformat(timespec="seconds"),
        "latest": latest_dt.isoformat(timespec="seconds"),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "message_count": len(messages),
    }
    fm_yaml = yaml.safe_dump(frontmatter, sort_keys=False, default_flow_style=False).strip()

    lines = [
        "---",
        fm_yaml,
        "---",
        "",
        f"# {title}",
        "",
        f"Channel: #{channel.name} ({channel.id})",
        f"Window: {oldest_dt.isoformat(timespec='seconds')} to {latest_dt.isoformat(timespec='seconds')}",
        f"Messages captured: {len(messages)}",
        "",
        "## Messages",
        "",
    ]

    current_date = ""
    for message in messages:
        day, clock = _format_ts(message.ts)
        if day != current_date:
            current_date = day
            lines.extend([f"### {day}", ""])
        indent = "  " if message.is_thread_reply else ""
        marker = "  - Reply" if message.is_thread_reply else "-"
        text = _clean_slack_text(message.text, user_names)
        subtype = f" ({message.subtype})" if message.subtype else ""
        lines.append(f"{indent}{marker} {clock} - {message.author}{subtype}: {text}")
        for file_line in _file_lines(message.files):
            lines.append(f"{indent}{file_line}")
    if not messages:
        lines.append("_No messages found in this window._")

    lines.append("")
    return "\n".join(lines)


def fetch_channel_to_raw(
    paths: cfg.WikiPaths,
    client: SlackClient,
    channel: SlackChannel,
    *,
    days: int = 7,
    limit: int = 200,
    include_threads: bool = True,
) -> SlackFetchOutcome:
    latest_dt = datetime.now(timezone.utc)
    oldest_dt = latest_dt - timedelta(days=days)
    messages = fetch_messages(
        client,
        channel.id,
        oldest=oldest_dt.timestamp(),
        latest=latest_dt.timestamp(),
        limit=limit,
        include_threads=include_threads,
    )

    raw_dir = paths.raw / "slack"
    raw_dir.mkdir(parents=True, exist_ok=True)
    channel_slug = slugify.slugify(channel.name) or channel.id.lower()
    dest = raw_dir / f"slack-{latest_dt.date().isoformat()}-{channel_slug}-last-{days}-days.md"
    dest.write_text(
        render_digest(
            channel,
            messages,
            oldest_dt=oldest_dt,
            latest_dt=latest_dt,
            lookback_days=days,
        ),
        encoding="utf-8",
    )

    sync = ingest_raw.sync_file(paths, dest)
    return SlackFetchOutcome(
        channel=channel.name,
        channel_id=channel.id,
        result=sync.result,
        relpath=sync.relpath,
        source_id=sync.source_id,
        message_count=len(messages),
        message=sync.message,
    )
