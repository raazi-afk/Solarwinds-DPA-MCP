# DPA MCP Server

Read-only MCP server for SolarWinds Database Performance Analyzer (DPA).
Exposes 16 tools covering server info, monitored databases, dashboards, metrics, and SQL tuning.

## Requirements

- Python 3.x (stdlib only, no extra packages needed)
- `mcp` package: `pip install mcp`
- Access to a running DPA instance

## Setup

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
# edit .env with your values
```

Then run:

```bash
source .env
python3 server.py
```

## Claude Code / Claude Desktop config

Add to your MCP config (`~/.claude.json` for Claude Code, or `claude_desktop_config.json` for Claude Desktop):

```json
{
  "mcpServers": {
    "dpa": {
      "command": "python3",
      "args": ["/path/to/dpa/server.py"],
      "env": {
        "DPA_BASE_URL": "https://<dpa-host>:<port>",
        "DPA_USERNAME": "your_username",
        "DPA_PASSWORD": "your_password"
      }
    }
  }
}
```

## Tools

| Tool | Description |
|------|-------------|
| `get_server_info` | DPA version, timezone, license state |
| `get_user_info` | Current user role and permissions |
| `get_database_permissions` | Per-DB access rights for current user |
| `list_databases` | All monitored databases with status |
| `get_database(db_id)` | Full detail for a specific database |
| `get_top_instances` | DBs ranked by highest wait time (~14-day) |
| `get_upward_trends` | DBs with worsening wait time trend |
| `get_downward_trends` | DBs with improving wait time trend |
| `get_database_tab_health(db_id)` | Health/alarm level per tab (tuning, resources, etc.) |
| `get_database_permissions_detail(db_id)` | Per-DB permissions for current user |
| `list_metric_categories(db_id)` | Available metric categories and names |
| `get_metric_data(db_id, metrics, start_time, end_time)` | Time-series metric data |
| `get_tuning_dates(db_id)` | Dates with tuning advice and alarm levels |
| `get_sql_advices(db_id, date)` | Top problematic SQL queries for a date |
| `get_index_recommendations(db_id, day)` | Index recommendations with estimated savings |
| `list_sql_stat_types(db_id)` | Available SQL statistic types |

## Authentication

Uses session cookie auth (`JSESSIONID`) via form login at `/iwc/login.iwc`.
The server logs in automatically on startup and re-authenticates on session expiry.
Self-signed SSL certificates are accepted (no verification).
