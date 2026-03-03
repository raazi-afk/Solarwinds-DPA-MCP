# DPA MCP Server

Read-only [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) server for **SolarWinds Database Performance Analyzer (DPA)**.
Exposes **18 tools** that let AI assistants query DPA for server info, monitored databases, dashboards, performance metrics, SQL tuning advice, and individual SQL statement statistics.

## Requirements

- Python 3.10+
- [`mcp`](https://pypi.org/project/mcp/) package — `pip install mcp`
- Network access to a running DPA instance (HTTPS)

## Quick Start

Set the required environment variables and run the server:

```bash
export DPA_BASE_URL="https://<dpa-host>:<port>"
export DPA_USERNAME="your_username"
export DPA_PASSWORD="your_password"

python3 server.py
```

Or use a `.env` file:

```bash
cp .env.example .env   # fill in your values
source .env && python3 server.py
```

## MCP Client Configuration

### VS Code (Copilot / Cline / Continue)

Add to `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "dpa": {
      "type": "stdio",
      "command": "python3",
      "args": ["/path/to/dpa-mcp/server.py"],
      "env": {
        "DPA_BASE_URL": "https://<dpa-host>:<port>",
        "DPA_USERNAME": "your_username",
        "DPA_PASSWORD": "your_password"
      }
    }
  }
}
```

### Claude Code / Claude Desktop

Add to `~/.claude.json` (Claude Code) or `claude_desktop_config.json` (Claude Desktop):

```json
{
  "mcpServers": {
    "dpa": {
      "command": "python3",
      "args": ["/path/to/dpa-mcp/server.py"],
      "env": {
        "DPA_BASE_URL": "https://<dpa-host>:<port>",
        "DPA_USERNAME": "your_username",
        "DPA_PASSWORD": "your_password"
      }
    }
  }
}
```

## Tools (18)

### Server & User

| Tool | Description |
|------|-------------|
| `get_server_info` | DPA version, timezone, license state, repository type, server time |
| `get_user_info` | Current authenticated user's role and permissions |
| `get_database_permissions` | Per-database access rights for the current user |

### Databases

| Tool | Description |
|------|-------------|
| `list_databases` | All monitored databases with status, type, version, and feature flags |
| `get_database(db_id)` | Full detail for a single monitored database |
| `get_database_tab_health(db_id)` | Health/alarm level per tab (tuning, trends, resources, AG) |
| `get_database_permissions_detail(db_id)` | Current user's permissions for a specific database |

### Dashboards

| Tool | Description |
|------|-------------|
| `get_top_instances` | Databases ranked by highest wait time (~14 days) |
| `get_upward_trends` | Databases with worsening (increasing) wait time trend |
| `get_downward_trends` | Databases with improving (decreasing) wait time trend |

### Performance Metrics

| Tool | Description |
|------|-------------|
| `list_metric_categories(db_id)` | Available metric categories and metric names (CPU, Memory, Disk, etc.) |
| `get_metric_data(db_id, metrics, start_time, end_time)` | Time-series data for one or more performance metrics |

### SQL Tuning & Analysis

| Tool | Description |
|------|-------------|
| `get_tuning_dates(db_id)` | Recent dates with tuning advice, alarm levels, and advice counts |
| `get_sql_advices(db_id, date)` | Top problematic SQL queries for a given date with problem summaries |
| `get_index_recommendations(db_id, day)` | Index recommendations (CREATE INDEX SQL) with estimated wait time savings |
| `list_sql_stat_types(db_id)` | Available SQL statistic types (Executions, Disk Reads, Buffer Gets, etc.) |
| `find_sql_text(db_id, sqlHash, time_range_from, time_range_to, ...)` | Search for SQL statements by hash with execution statistics and filtering |
| `get_sql_stats(db_id, sql_hash, time_range_from, time_range_to)` | Detailed execution stats for a specific SQL statement (wait time, executions, users, machines) |

## Authentication

Uses session cookie auth (`JSESSIONID`) via form login at `/iwc/login.iwc`.
The server logs in automatically on startup and re-authenticates transparently on session expiry.
Self-signed SSL certificates are accepted (certificate verification is disabled).


The server is fully read-only — no write or configuration-changing endpoints are exposed.
