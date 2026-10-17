import httpx
import pytest

from cmt_mcp.client import CMTAuthError, CMTClient, clean


def make(fake):
    return CMTClient(transport=httpx.MockTransport(fake.handler))


def test_clean_strips_odata_and_expands_json():
    out = clean({"@odata.id": "x", "#Act": {}, "Id": 1, "AuthorsJson": '[{"a": 1}]', "BadJson": "{nope", "n": [{"@odata.type": "t", "k": 2}]})
    assert out == {"Id": 1, "Authors": [{"a": 1}], "BadJson": "{nope", "n": [{"k": 2}]}


def test_missing_credentials(monkeypatch):
    monkeypatch.delenv("CMT_EMAIL", raising=False)
    monkeypatch.delenv("CMT_PASSWORD", raising=False)
    with pytest.raises(CMTAuthError, match="CMT_EMAIL"):
        CMTClient()


async def test_lazy_login_then_reuse(fake):
    c = make(fake)
    await c.my_conferences()
    await c.my_conferences()
    assert fake.logins == 1


async def test_bad_password(fake, monkeypatch):
    monkeypatch.setenv("CMT_PASSWORD", "wrong")
    with pytest.raises(CMTAuthError, match="login failed"):
        await make(fake).my_conferences()


async def test_relogin_on_expired_session(fake):
    c = make(fake)
    await c.my_conferences()
    fake.session_valid = False  # server drops the session
    assert await c.my_conferences()
    assert fake.logins == 2


async def test_post_allowlist(fake):
    c = make(fake)
    with pytest.raises(PermissionError):
        await c.post_read("/Conf/Submissions(1)/Delete")
    with pytest.raises(PermissionError):
        await c._send("DELETE", "/Conf/Submissions(1)")
    with pytest.raises(PermissionError):
        await c._send("PUT", "/x")
    assert not [r for r in fake.requests if r[0] not in ("GET", "POST")]


async def test_summary_is_cleaned_and_id_is_int(fake):
    d = await make(fake).submission_summary("ConfA", "1")
    assert d["Authors"] == [{"FirstName": "A"}] and "@odata.type" not in d
    with pytest.raises(ValueError):
        await make(fake).submission_summary("ConfA", "1); drop")


async def test_search_escapes_quotes(fake):
    c = make(fake)
    seen = {}
    orig = c.get

    async def spy(path, params=None):
        seen.update(params or {})
        return {"value": [], "@odata.count": 0}

    c.get = spy
    await c.search_conferences("o'brien")
    assert "o''brien" in seen["$filter"]
