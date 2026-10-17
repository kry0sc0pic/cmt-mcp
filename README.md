# cmt-mcp

A **read-only** [MCP](https://modelcontextprotocol.io) server that lets agents look up an author's data in
Microsoft CMT (cmt3.research.microsoft.com): conferences, submissions, statuses and reviews.

> Unofficial. Not affiliated with or endorsed by Microsoft. It uses CMT's web API as a logged-in user;
> use it only with your own account and in line with CMT's terms.

## Tools

| Tool | Description |
|---|---|
| `list_my_conferences` | Conferences your account participates in |
| `search_conferences` | Search all CMT conferences by name / city / country / slug |
| `list_submissions` | Your submissions with status. **Omit `conference` to pull across all your conferences** |
| `get_submission_status_cache` | Last-known statuses from the local cache (no network) |
| `get_submission` | Full summary: authors, abstract, files, answers |
| `get_reviews` | Reviews visible to you for a submission |

`conference` is the URL segment, e.g. `MyConf2026` in `cmt3.research.microsoft.com/MyConf2026`.

### Status caching
Statuses are stored in SQLite (`.cache/cmt.db`, override with `CMT_CACHE`). Each submission records its current
and previous status plus `last_checked` / `last_changed`, so an agent can see that a paper moved from
*Pending* to *Reject*. Listings are cached for 15 min, summaries/reviews for 6 h; pass `refresh=true` to force a
live fetch. `status_changed` is true only on the call that fetched the change.

### Read-only by design
The client sends only `GET` requests plus one allowlisted read-only `POST` (`GetSummaryView`); anything else
raises `PermissionError`. No write tools exist.

## Setup

```sh
uv sync
claude mcp add cmt -e CMT_EMAIL=you@example.com -e CMT_PASSWORD=... -- uv --directory /path/to/cmt-mcp run cmt-mcp
```

Auth is a plain HTTP login (`CMT_EMAIL`, `CMT_PASSWORD`) with automatic re-login when the session expires.
Credentials are read from the environment and never written to disk. Accounts that require SSO/MFA are not supported.

## Development

```sh
uv run pytest
```

Tests use an in-memory fake CMT (`httpx.MockTransport`), so they need no network or credentials.

`tools/capture.py` opens a browser (Playwright) and records XHR traffic to `captures/` (git-ignored) for
discovering more endpoints. Captures contain personal data and session tokens; never commit them.
