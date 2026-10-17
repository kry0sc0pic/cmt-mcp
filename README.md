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
| `list_submissions` | Your submissions with status (compact: no abstract/files). **Omit `conference` to pull across all your conferences** |
| `get_delta` | What changed since the last `get_delta` call: status changes, new reviews, new submissions |
| `get_submission` | Full summary: authors, abstract, files, answers |
| `get_reviews` | Reviews visible to you for a submission |

`conference` is the URL segment, e.g. `MyConf2026` in `cmt3.research.microsoft.com/MyConf2026`.

### Change tracking (`get_delta`)
Submission statuses and review counts are kept in a local SQLite cache (`.cache/cmt.db`, override with
`CMT_CACHE`). `get_delta` fetches live data and reports only what changed since the previous `get_delta`
call (`status_changed`, `new_reviews`, `new`), then moves the baseline forward. The first call only records a
baseline. Pass `acknowledge=false` to peek without consuming the changes; `list_submissions` never consumes them.
Listings are cached for 15 min and summaries/reviews for 6 h; pass `refresh=true` to force a live fetch.

### Read-only by design
The client sends only `GET` requests plus one allowlisted read-only `POST` (`GetSummaryView`); anything else
raises `PermissionError`. No write tools exist.

## Setup

```sh
uv sync
claude mcp add cmt -e CMT_EMAIL=you@example.com -e CMT_PASSWORD=... -- uv --directory /path/to/cmt-mcp run cmt-mcp
```

### Hermes Agent

```sh
uv run cmt-mcp-register hermes --dry-run   # preview, password masked
uv run cmt-mcp-register hermes             # prompts for email + password, writes ~/.hermes/config.yaml
```

It prompts for your CMT email and a hidden password (or reads `CMT_EMAIL`/`CMT_PASSWORD` if set). This adds an `mcp_servers.cmt` entry (backing up the old file to `config.yaml.bak`; YAML comments are not preserved).
Then run `/reload-mcp` in Hermes or start a new `hermes chat`, and check with `hermes mcp test cmt`.

Auth is a plain HTTP login (`CMT_EMAIL`, `CMT_PASSWORD`) with automatic re-login when the session expires.
The server reads credentials from its environment and never writes them itself. Registering with an MCP client stores them in that client's config (Claude Code: `~/.claude.json`; Hermes: `~/.hermes/config.yaml`, set to mode 600), so keep those files private. Accounts that require SSO/MFA are not supported.

## Development

```sh
uv run pytest
```

Tests use an in-memory fake CMT (`httpx.MockTransport`), so they need no network or credentials.

`tools/capture.py` opens a browser (Playwright) and records XHR traffic to `captures/` (git-ignored) for
discovering more endpoints. Captures contain personal data and session tokens; never commit them.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
