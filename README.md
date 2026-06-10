# Digital Twin Connector

Async Python module for ingesting data from GitHub, Google Drive, Gmail,
Google Calendar, Slack, and Jira through Model Context Protocol (MCP) servers.

The main entrypoint is `digital_twin_ingestor.py`, which defines
`DigitalTwinIngestor`.

## What This Project Does

- Starts MCP servers as background subprocesses through `npx`.
- Manages multiple MCP sessions with `contextlib.AsyncExitStack`.
- Uses async Python (`asyncio`, `async` / `await`) end to end.
- Loads credentials from `.env` with `python-dotenv`.
- Calls MCP tools dynamically with:

```python
await ingestor.fetch_data(
    platform_name="github",
    tool_name="get_issue",
    arguments={"owner": "owner", "repo": "repo", "issue_number": 1},
)
```

## Requirements

- Windows PowerShell
- Python 3.12+ recommended
- Node.js, npm, and npx
- Network access for:
  - Python packages from PyPI
  - MCP server packages from npm

Check local versions:

```powershell
python --version
node --version
npm --version
npx --version
```

This workspace was initially created with Python `3.14.3`. If dependency
installation fails because a package does not support Python 3.14 yet, install
Python 3.12 and recreate the virtual environment with Python 3.12.

## Project Files

```text
digital_twin_ingestor.py  Main async MCP ingestor module
requirements.txt         Python dependencies
.env.example             Template for local credentials
.gitignore               Ignore rules for venv, caches, logs, and secrets
README.md                Setup and usage guide
```

## Setup

From the project root:

```powershell
cd C:\development\py-data-connector
```

Create a virtual environment:

```powershell
python -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

If PowerShell blocks script activation, run:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then open a new PowerShell terminal and activate `.venv` again.

## If You Need Python 3.12

Install Python 3.12, then recreate the virtual environment:

```powershell
Remove-Item .venv -Recurse -Force
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If the `py` launcher is not available, use the full path to your Python 3.12
executable.

## Environment Variables

Create your local `.env` file from the template:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` and fill in your real values.

```dotenv
# GitHub MCP server
GITHUB_PERSONAL_ACCESS_TOKEN=
GITHUB_OWNER=
GITHUB_REPO=
GITHUB_ISSUE_NUMBER=1

# Google OAuth client for Google Drive / Gmail / Calendar MCP servers
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Google Drive demo input
GOOGLE_DRIVE_FILE_ID=

# Google Calendar demo input
GOOGLE_CALENDAR_MAX_RESULTS=10
GOOGLE_CALENDAR_TIME_MIN=
GOOGLE_CALENDAR_TIME_MAX=

# Gmail MCP server
GMAIL_SEARCH_QUERY=in:inbox
GMAIL_MAX_RESULTS=10

# Slack MCP server
SLACK_BOT_TOKEN=
SLACK_TEAM_ID=
SLACK_CHANNEL_IDS=
SLACK_CHANNEL_LIMIT=20

# Jira MCP server
JIRA_BASE_URL=
JIRA_EMAIL=
JIRA_API_TOKEN=

# Optional logging
LOG_LEVEL=INFO
```

Never commit `.env`. It is ignored by `.gitignore`.

## Credentials You Must Prepare

GitHub:

- Create a GitHub Personal Access Token.
- Put it in `GITHUB_PERSONAL_ACCESS_TOKEN`.
- Set `GITHUB_OWNER`, `GITHUB_REPO`, and `GITHUB_ISSUE_NUMBER` for the demo.

Google Drive, Gmail, and Google Calendar:

- Create OAuth credentials in Google Cloud Console.
- Fill `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
- Set `GOOGLE_DRIVE_FILE_ID` to a file you want to read.
- The app creates `.mcp/gcp-oauth.keys.json` from these values for the Google
  Drive MCP server.
- Run the Google Drive auth flow once before using Drive ingestion.

Gmail:

- Enable the Gmail API in the same Google Cloud project.
- Add Gmail scopes to your OAuth consent screen:
  `https://www.googleapis.com/auth/gmail.modify` and
  `https://www.googleapis.com/auth/gmail.settings.basic`.
- Run the Gmail auth flow once before using Gmail ingestion.

Google Calendar:

- Enable the Google Calendar API in the same Google Cloud project.
- Add the Calendar scope to your OAuth consent screen:
  `https://www.googleapis.com/auth/calendar`.
- Run the Calendar auth flow once before using Calendar ingestion.

Slack:

- Create a Slack app at `https://api.slack.com/apps`.
- Add bot scopes:
  `channels:history`, `channels:read`, `chat:write`, `reactions:write`,
  `users:read`, and `users.profile:read`.
- Install the app to your workspace.
- Put the Bot User OAuth Token in `SLACK_BOT_TOKEN`.
- Put your workspace ID in `SLACK_TEAM_ID`.
- Optionally set `SLACK_CHANNEL_IDS` to a comma-separated allowlist of channel
  IDs.

Jira:

- Create an Atlassian API token at
  `https://id.atlassian.com/manage-profile/security/api-tokens`.
- Put your Jira URL in `JIRA_BASE_URL`, for example
  `https://your-company.atlassian.net`.
- Put your Atlassian account email in `JIRA_EMAIL`.
- Put the generated token in `JIRA_API_TOKEN`.

## MCP Servers Used

The Python module starts these servers with `npx`:

```text
GitHub:          npx -y @modelcontextprotocol/server-github
Google Drive:    npx -y @modelcontextprotocol/server-gdrive
Gmail:           npx -y @gongrzhe/server-gmail-autoauth-mcp
Google Calendar: npx -y @gongrzhe/server-calendar-autoauth-mcp
Slack:           npx -y @modelcontextprotocol/server-slack
Jira:            npx -y mcp-jira-stdio
```

The first run may take longer because `npx` downloads the server packages.

Important package status as of this project setup:

- `@modelcontextprotocol/server-github` exists but is deprecated on npm.
- `@modelcontextprotocol/server-gdrive` exists but is deprecated on npm.
- `@modelcontextprotocol/server-slack` exists but is deprecated on npm.
- `mcp-jira-stdio` is used for Jira Cloud/Server API access.
- `@modelcontextprotocol/server-gmail` currently returns `404` on npm.
- `@modelcontextprotocol/server-google-calendar` currently returns `404` on npm.
- The project uses working replacement packages for Gmail and Calendar:
  `@gongrzhe/server-gmail-autoauth-mcp` and
  `@gongrzhe/server-calendar-autoauth-mcp`.

## Slack Setup

1. Create a Slack app from scratch at `https://api.slack.com/apps`.
2. Go to OAuth & Permissions.
3. Add these Bot Token Scopes:

```text
channels:history
channels:read
chat:write
reactions:write
users:read
users.profile:read
```

4. Install the app to your workspace.
5. Copy the Bot User OAuth Token, which starts with `xoxb-`.
6. Find your workspace/team ID, which starts with `T`.
7. Add these values to `.env`:

```dotenv
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_TEAM_ID=T01234567
SLACK_CHANNEL_IDS=
SLACK_CHANNEL_LIMIT=20
```

If you set `SLACK_CHANNEL_IDS`, use channel IDs such as `C01234567`, separated
by commas. Leave it empty to let the server list public channels.

## Jira Setup

1. Open Atlassian API tokens:
   `https://id.atlassian.com/manage-profile/security/api-tokens`.
2. Create a token and copy it immediately.
3. Add these values to `.env`:

```dotenv
JIRA_BASE_URL=https://your-company.atlassian.net
JIRA_EMAIL=your-email@example.com
JIRA_API_TOKEN=your-api-token
```

The demo uses the read-only tool `jira_get_visible_projects`. Other useful
tools exposed by `mcp-jira-stdio` include:

```text
jira_get_visible_projects
jira_get_project_info
jira_get_issue
jira_search_issues
jira_get_my_issues
jira_get_users
```

## Google Drive Auth

The Google Drive MCP server does not use `GOOGLE_CLIENT_ID` and
`GOOGLE_CLIENT_SECRET` directly. The Python module converts them into:

```text
.mcp/gcp-oauth.keys.json
```

It also tells the server to store OAuth credentials at:

```text
.mcp/gdrive-credentials.json
```

Run this once after filling `.env`:

```powershell
$env:GDRIVE_OAUTH_PATH = "C:\development\py-data-connector\.mcp\gcp-oauth.keys.json"
$env:GDRIVE_CREDENTIALS_PATH = "C:\development\py-data-connector\.mcp\gdrive-credentials.json"
npx -y @modelcontextprotocol/server-gdrive auth
```

Complete the browser OAuth flow. After that, run the Python demo again.

## Gmail Auth

Create the global Gmail MCP config folder:

```powershell
New-Item -ItemType Directory -Force -Path C:\Users\trana\.gmail-mcp
Copy-Item .mcp\gcp-oauth.keys.json gcp-oauth.keys.json -Force
npx -y @gongrzhe/server-gmail-autoauth-mcp auth
Remove-Item gcp-oauth.keys.json -Force
```

Complete the browser OAuth flow. Credentials are saved to:

```text
C:\Users\trana\.gmail-mcp\credentials.json
```

## Google Calendar Auth

Create the global Calendar MCP config folder:

```powershell
New-Item -ItemType Directory -Force -Path C:\Users\trana\.calendar-mcp
Copy-Item .mcp\gcp-oauth.keys.json gcp-oauth.keys.json -Force
npx -y @gongrzhe/server-calendar-autoauth-mcp auth
Remove-Item gcp-oauth.keys.json -Force
```

Complete the browser OAuth flow. Credentials are saved to:

```text
C:\Users\trana\.calendar-mcp\credentials.json
```

### If Google Shows "Access blocked"

If Chrome opens and Google shows:

```text
Access blocked: digital-twin-connectors has not completed the Google
verification process
```

fix the OAuth consent screen in Google Cloud Console:

1. Open Google Cloud Console for the same project as your OAuth client.
2. Go to Google Auth Platform / OAuth consent screen.
3. Set the app audience to `Testing` for local development.
4. Add your own Google account as a test user.
5. Make sure the Google Drive API is enabled.
6. Make sure the Drive scope is declared:

```text
https://www.googleapis.com/auth/drive.readonly
```

Then rerun:

```powershell
$env:GDRIVE_OAUTH_PATH = "C:\development\py-data-connector\.mcp\gcp-oauth.keys.json"
$env:GDRIVE_CREDENTIALS_PATH = "C:\development\py-data-connector\.mcp\gdrive-credentials.json"
npx -y @modelcontextprotocol/server-gdrive auth
```

For personal/local development, you do not need full production verification if
you keep the app in testing mode and only use accounts listed as test users.
For public use, Google requires brand and data-access verification for sensitive
or restricted scopes.

## Run The Demo

After installing dependencies and filling `.env`:

```powershell
.\.venv\Scripts\Activate.ps1
python digital_twin_ingestor.py
```

The demo will:

1. Connect to all configured MCP servers.
2. Call GitHub tool `get_issue`.
3. Read a Google Drive file through MCP resource `gdrive:///<file_id>`.
4. Call Gmail tool `search_emails`.
5. Call Google Calendar tool `list_events`.
6. Call Slack tool `slack_list_channels`.
7. Call Jira tool `jira_get_visible_projects`.
8. Close all MCP sessions on exit.

## Use As A Module

```python
import asyncio

from digital_twin_ingestor import DigitalTwinIngestor


async def main() -> None:
    async with DigitalTwinIngestor() as ingestor:
        await ingestor.connect("github")
        issue = await ingestor.fetch_data(
            platform_name="github",
            tool_name="get_issue",
            arguments={
                "owner": "your-org",
                "repo": "your-repo",
                "issue_number": 1,
            },
        )
        print(issue)


if __name__ == "__main__":
    asyncio.run(main())
```

## Common Problems

Dependency installation times out:

- Check internet access.
- Retry `python -m pip install -r requirements.txt`.
- If Python 3.14 causes compatibility issues, recreate `.venv` with Python 3.12.

`MissingEnvironmentError`:

- A required variable is missing from `.env`.
- Compare your `.env` with `.env.example`.

`ToolNotFoundError`:

- The MCP server connected, but the tool name does not exist on that server.
- Confirm the exact tool name exposed by the MCP server version you installed.

`npx` is not recognized:

- Install Node.js.
- Restart PowerShell.
- Confirm with `node --version` and `npx --version`.

MCP server startup is slow:

- This is normal on first run because `npx -y` may download npm packages.

## Development Checks

Compile-check the module:

```powershell
python -m py_compile digital_twin_ingestor.py
```

Check git status:

```powershell
git status --short
```
