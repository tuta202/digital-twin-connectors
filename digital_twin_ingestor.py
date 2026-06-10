"""Async MCP ingestor for GitHub, Google Workspace, Slack, and Jira."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from contextlib import AsyncExitStack
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import AnyUrl


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent
MCP_STATE_DIR = PROJECT_ROOT / ".mcp"
GOOGLE_ENV = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET")
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"

CredentialStrategy = Literal["none", "gdrive", "google_autoauth"]


class IngestorError(Exception):
    """Base error raised by the digital twin ingestor."""


class MissingEnvironmentError(IngestorError):
    """Raised when required credentials are missing."""


class PlatformNotConnectedError(IngestorError):
    """Raised when a platform session has not been initialized."""


class ToolNotFoundError(IngestorError):
    """Raised when a requested MCP tool is unavailable on a platform."""


class ToolCallError(IngestorError):
    """Raised when an MCP tool call fails or returns an invalid response."""


@dataclass(frozen=True)
class ServerConfig:
    """Configuration needed to start and validate one MCP server."""

    name: str
    package: str
    required_env: tuple[str, ...]
    optional_env: tuple[str, ...] = ()
    credential_strategy: CredentialStrategy = "none"


@dataclass
class ServerSession:
    """Active MCP session plus its discovered tool names."""

    session: ClientSession
    tools: set[str]


DEFAULT_SERVERS: tuple[ServerConfig, ...] = (
    ServerConfig(
        name="github",
        package="@modelcontextprotocol/server-github",
        required_env=("GITHUB_PERSONAL_ACCESS_TOKEN",),
    ),
    ServerConfig(
        name="gdrive",
        package="@modelcontextprotocol/server-gdrive",
        required_env=GOOGLE_ENV,
        credential_strategy="gdrive",
    ),
    ServerConfig(
        name="gmail",
        package="@gongrzhe/server-gmail-autoauth-mcp",
        required_env=GOOGLE_ENV,
        credential_strategy="google_autoauth",
    ),
    ServerConfig(
        name="calendar",
        package="@gongrzhe/server-calendar-autoauth-mcp",
        required_env=GOOGLE_ENV,
        credential_strategy="google_autoauth",
    ),
    ServerConfig(
        name="slack",
        package="@modelcontextprotocol/server-slack",
        required_env=("SLACK_BOT_TOKEN", "SLACK_TEAM_ID"),
        optional_env=("SLACK_CHANNEL_IDS",),
    ),
    ServerConfig(
        name="jira",
        package="mcp-jira-stdio",
        required_env=("JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"),
    ),
)


class DigitalTwinIngestor:
    """Manage async MCP server sessions and call their tools/resources."""

    def __init__(
        self,
        servers: tuple[ServerConfig, ...] = DEFAULT_SERVERS,
        connect_timeout: float = 30.0,
        tool_timeout: float = 60.0,
    ) -> None:
        """Load environment variables and prepare lazy MCP connections."""
        load_dotenv()
        self._server_configs = {server.name: server for server in servers}
        self._connect_timeout = connect_timeout
        self._tool_timeout = tool_timeout
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, ServerSession] = {}
        self._closed = False

    async def __aenter__(self) -> "DigitalTwinIngestor":
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.cleanup()

    @property
    def connected_platforms(self) -> tuple[str, ...]:
        """Return currently connected platform names."""
        return tuple(sorted(self._sessions))

    async def connect_all(self) -> None:
        """Connect to every configured MCP server."""
        for platform_name in self._server_configs:
            await self.connect(platform_name)

    async def connect(self, platform_name: str) -> None:
        """Start one MCP server process and initialize its session."""
        self._ensure_open()
        platform_name = self._normalize_platform(platform_name)
        if platform_name in self._sessions:
            LOGGER.debug("Platform %s is already connected.", platform_name)
            return

        config = self._server_configs[platform_name]
        self._validate_environment(config)
        params = self._server_parameters(config)

        LOGGER.info("Starting MCP server for platform %s.", platform_name)
        try:
            async with asyncio.timeout(self._connect_timeout):
                read_stream, write_stream = await self._exit_stack.enter_async_context(
                    stdio_client(params)
                )
                session = await self._exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()
                tools_response = await session.list_tools()
        except TimeoutError as exc:
            LOGGER.exception("Timed out connecting to MCP platform %s.", platform_name)
            raise IngestorError(
                f"Timed out connecting to MCP platform '{platform_name}'."
            ) from exc
        except Exception as exc:
            LOGGER.exception("Failed to initialize MCP platform %s.", platform_name)
            raise IngestorError(
                f"Failed to initialize MCP platform '{platform_name}'."
            ) from exc

        self._sessions[platform_name] = ServerSession(
            session=session,
            tools={tool.name for tool in tools_response.tools},
        )
        LOGGER.info(
            "Connected MCP platform %s with %d available tools.",
            platform_name,
            len(self._sessions[platform_name].tools),
        )

    async def fetch_data(
        self,
        platform_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> str:
        """Call an MCP tool dynamically and return the first text payload."""
        server_session = self._session_for(platform_name)
        if tool_name not in server_session.tools:
            platform = self._normalize_platform(platform_name)
            LOGGER.error(
                "Tool %s is unavailable on %s. Available tools: %s",
                tool_name,
                platform,
                sorted(server_session.tools),
            )
            raise ToolNotFoundError(
                f"Tool '{tool_name}' is unavailable on '{platform}'."
            )

        LOGGER.info("Calling MCP tool %s on platform %s.", tool_name, platform_name)
        try:
            async with asyncio.timeout(self._tool_timeout):
                response = await server_session.session.call_tool(
                    tool_name,
                    arguments or {},
                )
        except TimeoutError as exc:
            raise ToolCallError(
                f"Timed out calling tool '{tool_name}' on '{platform_name}'."
            ) from exc
        except Exception as exc:
            LOGGER.exception("MCP tool %s failed on %s.", tool_name, platform_name)
            raise ToolCallError(
                f"Tool '{tool_name}' failed on '{platform_name}'."
            ) from exc

        return _extract_tool_text(response)

    async def read_resource(self, platform_name: str, uri: str) -> str:
        """Read an MCP resource and return the first text/blob payload."""
        server_session = self._session_for(platform_name)
        try:
            async with asyncio.timeout(self._tool_timeout):
                response = await server_session.session.read_resource(AnyUrl(uri))
        except TimeoutError as exc:
            raise ToolCallError(
                f"Timed out reading resource '{uri}' on '{platform_name}'."
            ) from exc
        except Exception as exc:
            LOGGER.exception("Failed reading resource %s on %s.", uri, platform_name)
            raise ToolCallError(
                f"Failed reading resource '{uri}' on '{platform_name}'."
            ) from exc

        return _extract_resource_text(response)

    async def cleanup(self) -> None:
        """Close all sessions and terminate MCP subprocesses."""
        if self._closed:
            return

        LOGGER.info("Closing %d MCP platform session(s).", len(self._sessions))
        self._sessions.clear()
        try:
            await self._exit_stack.aclose()
        except Exception:
            LOGGER.exception("Error while closing MCP sessions.")
            raise
        finally:
            self._closed = True

    def _server_parameters(self, config: ServerConfig) -> StdioServerParameters:
        return StdioServerParameters(
            command=_npx_command(),
            args=["-y", config.package],
            env=_build_server_environment(config),
        )

    def _session_for(self, platform_name: str) -> ServerSession:
        self._ensure_open()
        platform_name = self._normalize_platform(platform_name)
        session = self._sessions.get(platform_name)
        if session is None:
            raise PlatformNotConnectedError(
                f"Platform '{platform_name}' is not connected."
            )
        return session

    def _normalize_platform(self, platform_name: str) -> str:
        normalized = platform_name.lower()
        if normalized not in self._server_configs:
            raise ValueError(f"Unknown platform '{platform_name}'.")
        return normalized

    def _validate_environment(self, config: ServerConfig) -> None:
        missing = [name for name in config.required_env if not os.getenv(name)]
        if missing:
            raise MissingEnvironmentError(
                f"Missing environment variables for '{config.name}': "
                f"{', '.join(missing)}"
            )

    def _ensure_open(self) -> None:
        if self._closed:
            raise IngestorError("DigitalTwinIngestor has already been closed.")


def _build_server_environment(config: ServerConfig) -> dict[str, str]:
    env = dict(os.environ)
    for key in config.required_env:
        env[key] = os.environ[key]
    for key in config.optional_env:
        value = os.getenv(key)
        if value:
            env[key] = value

    if config.credential_strategy == "gdrive":
        _configure_gdrive(env)
    elif config.credential_strategy == "google_autoauth":
        _configure_google_autoauth(config, env)

    return env


def _configure_gdrive(env: dict[str, str]) -> None:
    MCP_STATE_DIR.mkdir(exist_ok=True)
    oauth_path = Path(
        env.get("GDRIVE_OAUTH_PATH", MCP_STATE_DIR / "gcp-oauth.keys.json")
    )
    credentials_path = Path(
        env.get("GDRIVE_CREDENTIALS_PATH", MCP_STATE_DIR / "gdrive-credentials.json")
    )

    _ensure_google_oauth_file(oauth_path, env)
    env["GDRIVE_OAUTH_PATH"] = str(oauth_path)
    env["GDRIVE_CREDENTIALS_PATH"] = str(credentials_path)

    if not credentials_path.exists():
        raise MissingEnvironmentError(
            "Google Drive credentials are missing. Run the Drive auth flow "
            f"first so '{credentials_path}' is created."
        )


def _configure_google_autoauth(config: ServerConfig, env: dict[str, str]) -> None:
    config_dir = Path.home() / f".{config.name}-mcp"
    config_dir.mkdir(exist_ok=True)
    _ensure_google_oauth_file(config_dir / "gcp-oauth.keys.json", env)

    credentials_path = config_dir / "credentials.json"
    if not credentials_path.exists():
        raise MissingEnvironmentError(
            f"Google {config.name.title()} credentials are missing. "
            f"Run 'npx -y {config.package} auth' first."
        )


def _ensure_google_oauth_file(path: Path, env: dict[str, str]) -> None:
    if path.exists():
        return

    payload = {
        "installed": {
            "client_id": env["GOOGLE_CLIENT_ID"],
            "client_secret": env["GOOGLE_CLIENT_SECRET"],
            "redirect_uris": ["http://localhost"],
            "auth_uri": GOOGLE_AUTH_URI,
            "token_uri": GOOGLE_TOKEN_URI,
        }
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _npx_command() -> str:
    return "npx.cmd" if sys.platform.startswith("win") else "npx"


def _extract_tool_text(response: Any) -> str:
    try:
        text = response.content[0].text
    except (AttributeError, IndexError, TypeError) as exc:
        LOGGER.error("MCP response did not include text content: %r", response)
        raise ToolCallError("MCP response did not include text content.") from exc

    if not isinstance(text, str):
        raise ToolCallError("MCP response text content was not a string.")
    return text


def _extract_resource_text(response: Any) -> str:
    try:
        first_content = response.contents[0]
    except (AttributeError, IndexError, TypeError) as exc:
        LOGGER.error("MCP response did not include resource content: %r", response)
        raise ToolCallError("MCP response did not include resource content.") from exc

    text = getattr(first_content, "text", None)
    if isinstance(text, str):
        return text

    blob = getattr(first_content, "blob", None)
    if isinstance(blob, str):
        return blob

    raise ToolCallError("MCP resource content was not text or blob content.")


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Register process termination handlers for graceful shutdown."""
    loop = asyncio.get_running_loop()

    def request_stop() -> None:
        LOGGER.info("Shutdown signal received.")
        stop_event.set()

    for signal_name in ("SIGINT", "SIGTERM"):
        current_signal = getattr(signal, signal_name, None)
        if current_signal is None:
            continue
        try:
            loop.add_signal_handler(current_signal, request_stop)
        except (NotImplementedError, RuntimeError):
            signal.signal(current_signal, lambda *_args: request_stop())


def _calendar_window() -> dict[str, str]:
    now = datetime.now(UTC)
    return {
        "timeMin": os.environ.get(
            "GOOGLE_CALENDAR_TIME_MIN",
            now.isoformat().replace("+00:00", "Z"),
        ),
        "timeMax": os.environ.get(
            "GOOGLE_CALENDAR_TIME_MAX",
            (now + timedelta(days=30)).isoformat().replace("+00:00", "Z"),
        ),
    }


async def _demo() -> None:
    """Run a minimal end-to-end demo against all configured MCP servers."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)

    async with DigitalTwinIngestor() as ingestor:
        await ingestor.connect_all()

        github_issue = await ingestor.fetch_data(
            "github",
            "get_issue",
            {
                "owner": os.environ["GITHUB_OWNER"],
                "repo": os.environ["GITHUB_REPO"],
                "issue_number": int(os.environ.get("GITHUB_ISSUE_NUMBER", "1")),
            },
        )
        LOGGER.info("GitHub issue payload:\n%s", github_issue)

        drive_file = await ingestor.read_resource(
            "gdrive",
            f"gdrive:///{os.environ['GOOGLE_DRIVE_FILE_ID']}",
        )
        LOGGER.info("Google Drive file payload:\n%s", drive_file)

        gmail_messages = await ingestor.fetch_data(
            "gmail",
            "search_emails",
            {
                "query": os.environ.get("GMAIL_SEARCH_QUERY", "in:inbox"),
                "maxResults": int(os.environ.get("GMAIL_MAX_RESULTS", "10")),
            },
        )
        LOGGER.info("Gmail messages payload:\n%s", gmail_messages)

        calendar_args = {
            **_calendar_window(),
            "maxResults": int(os.environ.get("GOOGLE_CALENDAR_MAX_RESULTS", "10")),
        }
        calendar_events = await ingestor.fetch_data(
            "calendar",
            "list_events",
            calendar_args,
        )
        LOGGER.info("Google Calendar events payload:\n%s", calendar_events)

        slack_channels = await ingestor.fetch_data(
            "slack",
            "slack_list_channels",
            {"limit": int(os.environ.get("SLACK_CHANNEL_LIMIT", "20"))},
        )
        LOGGER.info("Slack channels payload:\n%s", slack_channels)

        jira_projects = await ingestor.fetch_data(
            "jira",
            "jira_get_visible_projects",
            {},
        )
        LOGGER.info("Jira projects payload:\n%s", jira_projects)

        if stop_event.is_set():
            LOGGER.info("Demo stopped by signal.")


if __name__ == "__main__":
    asyncio.run(_demo())
