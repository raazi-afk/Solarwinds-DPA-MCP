"""
DPA MCP Server — read-only tools for SolarWinds Database Performance Analyzer.
Auth: session cookie (username/password login via /iwc/login.iwc).
"""

import os
import json
import urllib.request
import urllib.parse
import urllib.error
import ssl
import http.cookiejar
from typing import Any

from mcp.server.fastmcp import FastMCP

# ── Config (env vars with fallbacks) ─────────────────────────────────────────
DPA_BASE = os.environ.get("DPA_BASE_URL", "https://localhost:8124")
DPA_USER = os.environ.get("DPA_USERNAME", "")
DPA_PASS = os.environ.get("DPA_PASSWORD", "")

# ── HTTP session ──────────────────────────────────────────────────────────────
# Ignore self-signed cert
_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_cookie_jar = http.cookiejar.CookieJar()
_opener = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=_ssl_ctx),
    urllib.request.HTTPCookieProcessor(_cookie_jar),
)

# Cached session credentials — refreshed on every login
_jsessionid: str = ""
_csrf_token: str = ""


def _extract_jsessionid() -> str:
    """Pull the current JSESSIONID value out of the shared cookie jar."""
    for cookie in _cookie_jar:
        if cookie.name == "JSESSIONID":
            return cookie.value
    return ""


def _extract_csrf_from_html(html: str) -> str:
    """Extract the Spring Security CSRF token from an HTML page."""
    for marker in [
        'name="_csrf" content="',   # <meta name="_csrf" content="TOKEN">
        'name="_csrf" value="',     # <input type="hidden" name="_csrf" value="TOKEN">
    ]:
        idx = html.find(marker)
        if idx != -1:
            start = idx + len(marker)
            return html[start:html.index('"', start)]
    return ""


def _get(path: str, params: dict | None = None) -> Any:
    """GET a /iwc/rest/ endpoint, auto-login if needed. Returns parsed JSON data."""
    url = DPA_BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with _opener.open(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            # If we got redirected to the login page the session expired
            if isinstance(body, dict) and "data" in body:
                return body["data"]
            # Unexpected shape — return raw
            return body
    except urllib.error.HTTPError as e:
        if e.code == 302:
            _login()
            return _get(path, params)
        raise RuntimeError(f"HTTP {e.code} from {path}: {e.read().decode()[:200]}")


def _post(path: str, payload: dict) -> Any:
    """POST JSON to a /iwc/rest/ endpoint, auto-login if needed. Returns parsed JSON data."""
    url = DPA_BASE + path
    data = json.dumps(payload).encode()
    # Let HTTPCookieProcessor send all cookies automatically (same as _get).
    # Do NOT manually set Cookie here — it would overwrite the processor and
    # drop the second JSESSIONID that the server requires.
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if _csrf_token:
        headers["X-CSRF-TOKEN"] = _csrf_token
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with _opener.open(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
            if isinstance(body, dict) and "data" in body:
                return body["data"]
            return body
    except urllib.error.HTTPError as e:
        if e.code in (302, 401):
            _login()
            return _post(path, payload)
        raise RuntimeError(f"HTTP {e.code} from {path}: {e.read().decode()[:200]}")


def _login() -> None:
    """Log in to DPA and populate the cookie jar with a valid JSESSIONID."""
    global _jsessionid, _csrf_token

    # Step 1: GET login page to get JSESSIONID + CSRF token
    req = urllib.request.Request(
        DPA_BASE + "/iwc/login.iwc",
        headers={"Accept": "text/html"},
    )
    with _opener.open(req, timeout=10) as resp:
        html = resp.read().decode()

    # Extract CSRF token
    csrf = ""
    marker = 'name="_csrf" value="'
    idx = html.find(marker)
    if idx != -1:
        start = idx + len(marker)
        end = html.index('"', start)
        csrf = html[start:end]

    # Step 2: POST login
    data = urllib.parse.urlencode({
        "user": DPA_USER,
        "password": DPA_PASS,
        "_csrf": csrf,
    }).encode()

    req = urllib.request.Request(
        DPA_BASE + "/iwc/login.iwc",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    # Don't follow the redirect — we just want the Set-Cookie header
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def http_error_302(self, req, fp, code, msg, headers):
            return fp

    no_redirect_opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=_ssl_ctx),
        urllib.request.HTTPCookieProcessor(_cookie_jar),
        _NoRedirect(),
    )
    no_redirect_opener.open(req, timeout=10)

    # Cache the authenticated JSESSIONID so _post() can set it explicitly
    _jsessionid = _extract_jsessionid()

    # Step 3: fetch the main Angular page to obtain the authenticated CSRF token.
    # Spring Security stores the CSRF token in the session; DPA embeds it as a
    # meta tag in the app HTML so that the Angular client can read it.
    csrf_req = urllib.request.Request(
        DPA_BASE + "/iwc/ng/",
        headers={"Accept": "text/html"},
    )
    with _opener.open(csrf_req, timeout=10) as resp:
        _csrf_token = _extract_csrf_from_html(resp.read().decode())


# Login on startup
_login()

# ── MCP server ────────────────────────────────────────────────────────────────
mcp = FastMCP("dpa")


@mcp.tool()
def get_server_info() -> dict:
    """
    Return DPA server metadata: version, timezone, license state,
    repository type, and server time.
    """
    return _get("/iwc/rest/server-info")


@mcp.tool()
def get_user_info() -> dict:
    """
    Return information about the currently authenticated DPA user,
    including their role and permissions flags.
    """
    return _get("/iwc/rest/user-info")


@mcp.tool()
def get_database_permissions() -> dict:
    """
    Return the current user's per-database permissions: which database IDs
    they can view performance data for, manage alerts on, etc.
    """
    return _get("/iwc/rest/databases/permissions/details")


@mcp.tool()
def list_databases() -> list:
    """
    List all databases monitored by DPA.
    Each entry includes: id, name, type, version, monitoringState,
    deployment, host, lastDataPoint, and feature flags (PDB, RAC, etc.).
    """
    return _get("/iwc/rest/databases")


@mcp.tool()
def get_database(db_id: int) -> dict:
    """
    Return full detail for a single monitored database.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
    """
    return _get(f"/iwc/rest/databases/{db_id}")


@mcp.tool()
def get_top_instances() -> dict:
    """
    Return the 'Instances with highest wait time' dashboard chart data.
    Shows daily average wait time (seconds) per database over the last ~14 days.
    Useful for identifying which database is performing worst.
    """
    return _get("/iwc/rest/dashboards/top-instances", {"pm": "P"})


@mcp.tool()
def get_upward_trends() -> dict:
    """
    Return databases with the greatest upward (worsening) wait time trend.
    Shows the percentage increase in wait time per day over the last ~14 days.
    """
    return _get("/iwc/rest/dashboards/upwards-trends", {"pm": "P"})


@mcp.tool()
def get_downward_trends() -> dict:
    """
    Return databases with the greatest downward (improving) wait time trend.
    Shows the percentage decrease in wait time per day over the last ~14 days.
    """
    return _get("/iwc/rest/dashboards/downwards-trends", {"pm": "P"})


@mcp.tool()
def get_database_tab_health(db_id: int) -> dict:
    """
    Return the health/alarm level for each main tab of a database:
    tuning, trends, resources, and AG (availability group) health.
    Useful for a quick status overview before drilling in.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
    """
    return _get(f"/iwc/rest/databases/{db_id}/super-tab", {"pmCode": "P"})


@mcp.tool()
def get_database_permissions_detail(db_id: int) -> dict:
    """
    Return the current user's permissions for a specific database:
    viewPerformanceData, viewAlerts, manageAlerts, manageMonitoring, manageReporting.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
    """
    return _get(f"/iwc/rest/databases/{db_id}/permissions")


@mcp.tool()
def list_metric_categories(db_id: int) -> list:
    """
    Return all available performance metric categories and metric names for a database.
    Use this to discover valid metric names before calling get_metric_data.
    Categories include: Connections, CPU, Memory, Disk, Network, Sessions, Waits, etc.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
    """
    return _get(f"/iwc/rest/databases/{db_id}/metrics/categories", {"require": "metrics"})


@mcp.tool()
def get_metric_data(db_id: int, metrics: str, start_time: str, end_time: str) -> list:
    """
    Return time-series data for one or more performance metrics.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
        metrics: Comma-separated metric names, e.g. "CPU Utilization,Total User Sessions".
                 Use list_metric_categories to discover valid names.
        start_time: ISO 8601 start time, e.g. "2026-02-24T05:00:00Z".
        end_time:   ISO 8601 end time,   e.g. "2026-02-24T08:00:00Z".
    """
    return _get(f"/iwc/rest/databases/{db_id}/metrics/data", {
        "metrics": metrics,
        "startTime": start_time,
        "endTime": end_time,
        "useResourceGranularities": "true",
        "baseline": "false",
    })


@mcp.tool()
def get_tuning_dates(db_id: int) -> list:
    """
    Return a list of recent dates with tuning advice available, including:
    alarm level (WARNING/NORMAL), query advice count, and index advice count per day.
    Use this to find which days had the most problems before fetching sql_advices.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
    """
    return _get(f"/iwc/rest/databases/{db_id}/dates/tuning")


@mcp.tool()
def get_sql_advices(db_id: int, date: str) -> dict:
    """
    Return the top problematic SQL queries for a given date, including:
    sqlHash, sqlName, status (WARNING/etc), execution percentage, and
    human-readable problem summaries (e.g. "Had high executions during 4:00 AM hour").

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
        date:  Date in YYYY-MM-DD format, e.g. "2026-02-24".
               Use get_tuning_dates to find dates with issues.
    """
    return _get(f"/iwc/rest/databases/{db_id}/problems/sql-advices", {"date": date})


@mcp.tool()
def get_index_recommendations(db_id: int, day: str) -> dict:
    """
    Return index recommendations (what-if analysis) for a given day, including:
    the CREATE INDEX SQL, estimated wait time savings, schema, and table name.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
        day:   Date in YYYY-MM-DD format, e.g. "2026-02-23".
               Use get_tuning_dates to find days with index advice.
    """
    return _get(f"/iwc/rest/databases/{db_id}/what-if", {"day": day})


@mcp.tool()
def list_sql_stat_types(db_id: int) -> list:
    """
    Return the available SQL statistic types for a database
    (e.g. Executions, Disk Reads, Buffer Gets, Rows Processed, Sorts, Parses).
    These IDs can be used when analysing SQL performance characteristics.

    Args:
        db_id: The numeric database ID (e.g. 1 or 2).
    """
    return _get(f"/iwc/rest/databases/{db_id}/sql-stats/types")


@mcp.tool()
def find_sql_text(
    db_id: int,
    sqlHash: int,
    time_range_from: str,
    time_range_to: str,
    find_sql_search_mode: str | None = None,
    offset: int | None = None,
    limit: int | None = None,
    databases: list | None = None,
    db_users: list | None = None,
    machines: list | None = None,
    programs: list | None = None,
) -> dict:
    """
    Search for SQL statements on a monitored database by SQL hash.
    Returns a paginated list of matching queries with execution statistics.

    Args:
        db_id:                The numeric database ID (e.g. 1 or 2). Required.
        sqlHash:              The integer SQL hash identifying the query (e.g. 1101975711). Required.
        time_range_from:      ISO 8601 start time, e.g. "2026-02-24T07:00:00.000Z". Required.
        time_range_to:        ISO 8601 end time,   e.g. "2026-02-25T07:00:00.000Z". Required.
        find_sql_search_mode: Search mode: "SIMPLE" or "ADVANCED". Optional (defaults to "SIMPLE").
        offset:               Pagination offset. Optional (defaults to 0).
        limit:                Page size. Optional (defaults to 5).
        databases:            Filter by database name list. Optional (defaults to all).
        db_users:             Filter by DB user list. Optional (defaults to all).
        machines:             Filter by machine/host list. Optional (defaults to all).
        programs:             Filter by program/application list. Optional (defaults to all).
    """
    payload: dict = {
        "searchText": str(sqlHash),
        "timeRangeFrom": time_range_from,
        "timeRangeTo": time_range_to,
        "findSqlSearchMode": find_sql_search_mode if find_sql_search_mode is not None else "SIMPLE",
        "offset": offset if offset is not None else 0,
        "limit": limit if limit is not None else 5,
        "databases": databases if databases is not None else [],
        "dbUsers": db_users if db_users is not None else [],
        "machines": machines if machines is not None else [],
        "programs": programs if programs is not None else [],
    }
    return _post(f"/iwc/rest/find-sql/{db_id}", payload)


@mcp.tool()
def get_sql_stats(
    db_id: int,
    sql_hash: int,
    time_range_from: str | None = None,
    time_range_to: str | None = None,
) -> dict:
    """
    Return execution statistics for a specific SQL statement identified by its hash,
    over a given time range. Includes wait time breakdown, execution counts, and
    performance trends useful for diagnosing individual query problems.

    Args:
        db_id:           The numeric database ID (e.g. 53).
        sql_hash:        The integer SQL hash identifying the query
                         (e.g. 1101975711). Obtain from get_sql_advices.
        time_range_from: ISO 8601 start time, e.g. "2026-02-24T05:00:00.000Z". Optional.
        time_range_to:   ISO 8601 end time,   e.g. "2026-02-25T05:00:00.000Z". Optional.
    """
    payload: dict = {"sqlHash": sql_hash}
    if time_range_from is not None:
        payload["timeRangeFrom"] = time_range_from
    if time_range_to is not None:
        payload["timeRangeTo"] = time_range_to
    return _post(f"/iwc/rest/find-sql/{db_id}/stats", payload)


if __name__ == "__main__":
    mcp.run()
