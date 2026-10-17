import httpx
import pytest

from cmt_mcp import server
from cmt_mcp.cache import Cache
from cmt_mcp.client import CMTClient


@pytest.fixture
def cache(tmp_path):
    return Cache(tmp_path / "test.db")


def sub(id_, status_id=0, status_name=None, title="Paper", reviews=0):
    return {"Id": id_, "Title": title, "TrackName": "Main", "StatusId": status_id, "StatusName": status_name,
            "NumberOfReviews": reviews, "NumberOfMetaReviews": 0, "Abstract": "abs",
            "SubmissionFilesJson": "[]", "@odata.id": "x"}


class FakeCMT:
    """In-memory CMT: conf slug -> submissions list (mutable between calls)."""

    def __init__(self, confs):
        self.forbidden = []  # listed in MyConferences but 403 on submissions
        self.confs, self.logins, self.requests, self.session_valid = confs, 0, [], False

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/odata")
        self.requests.append((request.method, path))
        if path == "/Users/Login":
            self.logins += 1
            body = request.read()
            if b"good-pass" not in body:
                return httpx.Response(401, json={})
            self.session_valid = True
            return httpx.Response(200, headers={"set-cookie": ".AspNetCore.Cookies=abc; path=/"}, json={})
        if not self.session_valid:
            return httpx.Response(302, headers={"location": "/User/Login"})
        if path == "/MyConferences":
            return httpx.Response(200, json={"value": [{"Id": i, "UrlSegmentName": c, "@odata.id": "x"}
                                                       for i, c in enumerate([*self.confs, *self.forbidden])]})
        if path.endswith("/SubmissionAuthorViews"):
            conf = path.split("/")[1]
            if conf not in self.confs:
                return httpx.Response(403, json={})
            return httpx.Response(200, json={"value": self.confs[conf]})
        if path.endswith("/GetSummaryView"):
            return httpx.Response(200, json={"Id": 1, "AuthorsJson": '[{"FirstName":"A"}]', "@odata.type": "t"})
        if path.endswith("/Reviews"):
            return httpx.Response(200, json={"value": [{"Id": 9, "IsSubmitted": True}]})
        return httpx.Response(404, json={})


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("CMT_EMAIL", "a@example.com")
    monkeypatch.setenv("CMT_PASSWORD", "good-pass")
    f = FakeCMT({"ConfA": [sub(1, 3, "Reject", "Paper A")], "ConfB": [sub(2), sub(3, 4, "Desk Reject")]})
    return f


@pytest.fixture
def wired(fake, tmp_path, monkeypatch):
    """Server module wired to the fake CMT and a temp cache."""
    monkeypatch.setattr(server, "_cache_inst", Cache(tmp_path / "srv.db"))
    monkeypatch.setattr(server, "_client", CMTClient(transport=httpx.MockTransport(fake.handler)))
    return fake
