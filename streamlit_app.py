"""Streamlit demo UI for the DigitalTwinIngestor connectors."""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
from dotenv import load_dotenv

from digital_twin_ingestor import DigitalTwinIngestor


load_dotenv()

LOCAL_TZ = ZoneInfo(os.getenv("APP_TIMEZONE", "Asia/Bangkok"))
EMAIL_ID_PATTERN = re.compile(r"^ID:\s*(?P<id>\S+)", re.MULTILINE)


def run_async(coro: Awaitable[str]) -> str:
    """Run one async scenario from Streamlit's synchronous execution model."""
    return asyncio.run(coro)


async def call_tool(platform: str, tool: str, arguments: dict | None = None) -> str:
    async with DigitalTwinIngestor(connect_timeout=90, tool_timeout=90) as ingestor:
        await ingestor.connect(platform)
        return await ingestor.fetch_data(platform, tool, arguments or {})


async def read_resource(platform: str, uri: str) -> str:
    async with DigitalTwinIngestor(connect_timeout=90, tool_timeout=90) as ingestor:
        await ingestor.connect(platform)
        return await ingestor.read_resource(platform, uri)


def week_window() -> dict[str, str]:
    now = datetime.now(LOCAL_TZ)
    start = now - timedelta(days=now.weekday())
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return {"timeMin": start.isoformat(), "timeMax": end.isoformat()}


def today_gmail_query() -> str:
    now = datetime.now(LOCAL_TZ)
    tomorrow = now + timedelta(days=1)
    return f"after:{now:%Y/%m/%d} before:{tomorrow:%Y/%m/%d}"


async def calendar_this_week() -> str:
    args = {
        **week_window(),
        "maxResults": int(os.getenv("GOOGLE_CALENDAR_MAX_RESULTS", "20")),
    }
    return await call_tool("calendar", "list_events", args)


async def gmail_today_with_content() -> str:
    max_results = int(os.getenv("GMAIL_TODAY_MAX_RESULTS", "5"))
    search_result = await call_tool(
        "gmail",
        "search_emails",
        {"query": today_gmail_query(), "maxResults": max_results},
    )
    message_ids = EMAIL_ID_PATTERN.findall(search_result)
    if not message_ids:
        return f"{search_result}\n\nNo message IDs found to read."

    chunks = ["Search result:", search_result, "\nFull message content:"]
    async with DigitalTwinIngestor(connect_timeout=90, tool_timeout=90) as ingestor:
        await ingestor.connect("gmail")
        for message_id in message_ids[:max_results]:
            content = await ingestor.fetch_data(
                "gmail",
                "read_email",
                {"messageId": message_id},
            )
            chunks.append(f"\n---\nMessage ID: {message_id}\n{content}")
    return "\n".join(chunks)


async def github_configured_issue() -> str:
    return await call_tool(
        "github",
        "get_issue",
        {
            "owner": os.environ["GITHUB_OWNER"],
            "repo": os.environ["GITHUB_REPO"],
            "issue_number": int(os.getenv("GITHUB_ISSUE_NUMBER", "1")),
        },
    )


async def drive_configured_file() -> str:
    return await read_resource(
        "gdrive",
        f"gdrive:///{os.environ['GOOGLE_DRIVE_FILE_ID']}",
    )


async def slack_channels() -> str:
    return await call_tool(
        "slack",
        "slack_list_channels",
        {"limit": int(os.getenv("SLACK_CHANNEL_LIMIT", "20"))},
    )


async def slack_recent_messages() -> str:
    channel_id = os.getenv("SLACK_DEMO_CHANNEL_ID") or os.getenv(
        "SLACK_CHANNEL_IDS",
        "",
    )
    channel_id = channel_id.split(",")[0].strip()
    if not channel_id:
        return "Set SLACK_DEMO_CHANNEL_ID or SLACK_CHANNEL_IDS to read channel history."
    return await call_tool(
        "slack",
        "slack_get_channel_history",
        {
            "channel_id": channel_id,
            "limit": int(os.getenv("SLACK_HISTORY_LIMIT", "10")),
        },
    )


async def jira_projects() -> str:
    return await call_tool("jira", "jira_get_visible_projects")


async def jira_my_issues() -> str:
    return await call_tool("jira", "jira_get_my_issues")


def render_scenario(
    title: str,
    caption: str,
    button_label: str,
    scenario: Callable[[], Awaitable[str]],
) -> None:
    with st.container(border=True):
        st.subheader(title)
        st.caption(caption)
        if st.button(button_label, key=title, use_container_width=True):
            with st.spinner("Đang kết nối MCP server và lấy dữ liệu..."):
                try:
                    result = run_async(scenario())
                except Exception as exc:  # noqa: BLE001 - display actionable UI error
                    st.error(str(exc))
                else:
                    st.text_area("Kết quả", result, height=360)


def render_env_status() -> None:
    required = {
        "GitHub": ["GITHUB_PERSONAL_ACCESS_TOKEN", "GITHUB_OWNER", "GITHUB_REPO"],
        "Google": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
        "Drive": ["GOOGLE_DRIVE_FILE_ID"],
        "Slack": ["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"],
        "Jira": ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"],
    }
    cols = st.columns(len(required))
    for col, (group, names) in zip(cols, required.items(), strict=True):
        ready = all(os.getenv(name) for name in names)
        col.metric(group, "Ready" if ready else "Missing")


def main() -> None:
    st.set_page_config(page_title="Digital Twin Connectors", layout="wide")
    st.title("Digital Twin Connector Demo")
    st.caption("Chạy các kịch bản ingest dữ liệu qua MCP từ nhiều nền tảng.")

    render_env_status()

    tab_overview, tab_work, tab_comms, tab_knowledge = st.tabs(
        ["Tổng quan", "Công việc", "Giao tiếp", "Tri thức"]
    )

    with tab_overview:
        left, right = st.columns(2)
        with left:
            render_scenario(
                "Lịch họp tuần này",
                "Lấy các sự kiện Google Calendar trong tuần hiện tại.",
                "Lấy lịch họp",
                calendar_this_week,
            )
        with right:
            render_scenario(
                "Email hôm nay",
                "Search Gmail trong ngày hôm nay rồi đọc nội dung từng email.",
                "Lấy email hôm nay",
                gmail_today_with_content,
            )

    with tab_work:
        left, right = st.columns(2)
        with left:
            render_scenario(
                "Jira projects",
                "Liệt kê các Jira project mà tài khoản hiện tại thấy được.",
                "Lấy Jira projects",
                jira_projects,
            )
            render_scenario(
                "Jira việc của tôi",
                "Lấy các issue đang assign cho tài khoản Jira hiện tại.",
                "Lấy issue của tôi",
                jira_my_issues,
            )
        with right:
            render_scenario(
                "GitHub issue mẫu",
                "Lấy issue theo GITHUB_OWNER, GITHUB_REPO, GITHUB_ISSUE_NUMBER.",
                "Lấy GitHub issue",
                github_configured_issue,
            )

    with tab_comms:
        left, right = st.columns(2)
        with left:
            render_scenario(
                "Slack channels",
                "Liệt kê Slack channels theo quyền của bot token.",
                "Lấy danh sách channels",
                slack_channels,
            )
        with right:
            render_scenario(
                "Slack messages",
                "Đọc lịch sử channel từ SLACK_DEMO_CHANNEL_ID hoặc SLACK_CHANNEL_IDS.",
                "Lấy tin nhắn Slack",
                slack_recent_messages,
            )

    with tab_knowledge:
        render_scenario(
            "Google Drive file",
            "Đọc nội dung file Drive được cấu hình trong GOOGLE_DRIVE_FILE_ID.",
            "Đọc file Drive",
            drive_configured_file,
        )


if __name__ == "__main__":
    main()
