"""Read-only client for the CMT3 OData API (logs in with email/password, then uses the session cookie)."""
import asyncio
import json
import os
import re

import httpx

BASE = "https://cmt3.research.microsoft.com"
API = f"{BASE}/api/odata"
# POST endpoints that only read data (OData function-style actions).
READ_ONLY_POSTS = re.compile(r"/SubmissionViews\(\d+\)/GetSummaryView$")


class CMTAuthError(RuntimeError):
    pass


def clean(obj):
    """Drop OData metadata noise and expand *Json string fields."""
    if isinstance(obj, list):
        return [clean(x) for x in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if "@odata" in k or k.startswith("#"):
                continue
            if k.endswith("Json") and v is None:
                continue
            if k.endswith("Json") and isinstance(v, str):
                try:
                    out[k[:-4]] = clean(json.loads(v))
                    continue
                except ValueError:
                    pass
            out[k] = clean(v)
        return out
    return obj


class CMTClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.email = os.environ.get("CMT_EMAIL")
        self.password = os.environ.get("CMT_PASSWORD")
        if not (self.email and self.password):
            raise CMTAuthError("Set CMT_EMAIL and CMT_PASSWORD in the MCP server environment")
        self.http = httpx.AsyncClient(
            base_url=API, transport=transport, follow_redirects=False, timeout=30,
            headers={"Accept": "application/json;odata.metadata=full",
                     "OData-Version": "4.0", "OData-MaxVersion": "4.0"},
        )
        self._login_lock = asyncio.Lock()
        self._logged_in = False

    async def login(self):
        async with self._login_lock:
            self.http.cookies.clear()
            r = await self.http.post("/Users/Login", params={"ReturnUrl": "/"},
                                     json={"Request": {"Email": self.email, "Password": self.password}})
            if r.status_code != 200 or ".AspNetCore.Cookies" not in self.http.cookies:
                raise CMTAuthError(f"CMT login failed (HTTP {r.status_code}); check CMT_EMAIL/CMT_PASSWORD")
            self._logged_in = True

    async def _send(self, method: str, path: str, **kw):
        if method == "POST" and not READ_ONLY_POSTS.search(path):
            raise PermissionError(f"POST {path} is not allowlisted (server is read-only)")
        if method not in ("GET", "POST"):
            raise PermissionError(f"{method} not allowed")
        if not self._logged_in:
            await self.login()
        for attempt in (0, 1):
            r = await self.http.request(method, path, **kw)
            if r.status_code in (301, 302, 401) or "json" not in r.headers.get("content-type", ""):
                if attempt == 0:
                    await self.login()  # session expired: re-auth once, retry
                    continue
                raise CMTAuthError("CMT rejected the session after re-login")
            r.raise_for_status()
            return r.json()

    async def get(self, path: str, params: dict | None = None):
        return await self._send("GET", path, params=params)

    async def post_read(self, path: str, body: dict | None = None):
        return await self._send("POST", path, json=body or {})

    # --- typed helpers -------------------------------------------------
    async def my_conferences(self):
        d = await self.get("/MyConferences", {"$count": "true", "$top": 200, "$orderby": "EndDate desc"})
        return clean(d["value"])

    async def search_conferences(self, query: str = "", top: int = 50, skip: int = 0):
        q = query.replace("'", "''").lower()
        flt = " or ".join(f"contains(tolower({f}),tolower('{q}'))" for f in ("Name", "City", "Country", "UrlSegmentName"))
        d = await self.get("/Conferences", {"$count": "true", "$top": top, "$skip": skip,
                                            "$filter": flt, "$orderby": "EndDate desc"})
        return {"total": d.get("@odata.count"), "conferences": clean(d["value"])}

    async def submissions(self, conf: str):
        d = await self.get(f"/{conf}/SubmissionAuthorViews", {"$count": "true", "$orderby": "Id asc", "$top": 100})
        return clean(d["value"])

    async def submission_summary(self, conf: str, sid: int):
        return clean(await self.post_read(f"/{conf}/SubmissionViews({int(sid)})/GetSummaryView"))

    async def reviews(self, conf: str, sid: int):
        d = await self.get(f"/{conf}/Submissions({int(sid)})/Reviews")
        return clean(d["value"])
