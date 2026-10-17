"""Read-only MCP server for Microsoft CMT."""
import asyncio
import time
from datetime import datetime, timezone

from mcp.server.mcpserver import MCPServer

from .cache import DETAIL_TTL, STATUS_TTL, Cache
from .client import CMTClient, CMTAuthError

mcp = MCPServer("cmt")
_cache_inst: Cache | None = None
_client: CMTClient | None = None


def _cache() -> Cache:
    global _cache_inst
    if _cache_inst is None:
        _cache_inst = Cache()
    return _cache_inst


def client() -> CMTClient:
    global _client
    if _client is None:
        _client = CMTClient()
    return _client


def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds") if ts else None


def _status_view(row: dict) -> dict:
    name = row["status_name"] or ("Pending" if not row["status_id"] else f"Status {row['status_id']}")
    return {
        "conference": row["conference"], "submission_id": row["submission_id"], "title": row["title"],
        "track": row["track"], "status": name, "status_id": row["status_id"],
        "num_reviews": row["num_reviews"], "num_meta_reviews": row["num_meta_reviews"],
        "status_changed": row.get("changed", False),
        "previous_status": row["prev_status_name"] or row["prev_status_id"],
        "last_checked": _iso(row["last_checked"]), "last_changed": _iso(row["last_changed"]),
    }


async def _conf_submissions(conf: str, refresh: bool):
    key = f"subs:{conf}"
    subs = None if refresh else _cache().get(key, STATUS_TTL)
    if subs is None:
        subs = await client().submissions(conf)
        _cache().put(key, subs)
        return subs, [_cache().record_status(conf, s) for s in subs]
    return subs, [r for r in _cache().cached_statuses(conf)]


@mcp.tool()
async def list_my_conferences(refresh: bool = False) -> list[dict]:
    """List conferences the logged-in CMT user participates in (id, name, UrlSegmentName, dates, location)."""
    cached = None if refresh else _cache().get("myconfs", DETAIL_TTL)
    if cached is None:
        cached = await client().my_conferences()
        _cache().put("myconfs", cached)
    return cached


@mcp.tool()
async def search_conferences(query: str = "", top: int = 50, skip: int = 0) -> dict:
    """Search ALL CMT conferences (~10k) by name, city, country or UrlSegmentName. Paged via top/skip."""
    return await client().search_conferences(query, min(top, 100), skip)


@mcp.tool()
async def list_submissions(conference: str | None = None, refresh: bool = False) -> list[dict]:
    """List the user's submissions with status.

    conference: UrlSegmentName (e.g. 'MyConf2026'). If omitted, pulls submissions across ALL of the
    user's conferences. Statuses are cached (15 min) and tracked over time: each item includes
    status_changed / previous_status / last_changed. Set refresh=true to force a live fetch.
    """
    confs = [conference] if conference else [c["UrlSegmentName"] for c in await list_my_conferences(refresh)]
    sem = asyncio.Semaphore(4)

    async def one(conf):
        async with sem:
            try:
                subs, rows = await _conf_submissions(conf, refresh)
                return [_status_view(r) | {"abstract": next((s.get("Abstract") for s in subs if s["Id"] == r["submission_id"]), None),
                                           "files": next((s.get("SubmissionFiles") for s in subs if s["Id"] == r["submission_id"]), None)}
                        for r in rows]
            except CMTAuthError:
                raise
            except Exception as e:  # conferences where the user has no submissions/author role
                return [] if conference is None else [{"conference": conf, "error": str(e)}]

    return [item for batch in await asyncio.gather(*(one(c) for c in confs)) for item in batch]


@mcp.tool()
async def get_submission_status_cache(conference: str | None = None) -> list[dict]:
    """Return last-known submission statuses from the local cache without calling CMT (works offline)."""
    return [_status_view(r) for r in _cache().cached_statuses(conference)]


@mcp.tool()
async def get_submission(conference: str, submission_id: int, refresh: bool = False) -> dict:
    """Full submission summary: authors, abstract, files, subject areas, question answers, dates."""
    key = f"summary:{conference}:{submission_id}"
    d = None if refresh else _cache().get(key, DETAIL_TTL)
    if d is None:
        d = await client().submission_summary(conference, submission_id)
        _cache().put(key, d)
    return d


@mcp.tool()
async def get_reviews(conference: str, submission_id: int, refresh: bool = False) -> list[dict]:
    """Reviews (and their question/answer text) visible to the author for a submission."""
    key = f"reviews:{conference}:{submission_id}"
    d = None if refresh else _cache().get(key, DETAIL_TTL)
    if d is None:
        d = await client().reviews(conference, submission_id)
        _cache().put(key, d)
    return d


def main():
    mcp.run()


if __name__ == "__main__":
    main()
