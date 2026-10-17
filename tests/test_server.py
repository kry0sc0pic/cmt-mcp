from cmt_mcp import server


async def test_list_all_conferences_when_unspecified(wired):
    out = await server.list_submissions()
    assert {(r["conference"], r["submission_id"]) for r in out} == {("ConfA", 1), ("ConfB", 2), ("ConfB", 3)}
    by = {r["submission_id"]: r["status"] for r in out}
    assert by == {1: "Reject", 2: "Pending", 3: "Desk Reject"}


async def test_single_conference(wired):
    out = await server.list_submissions("ConfB")
    assert {r["submission_id"] for r in out} == {2, 3}


async def test_second_call_served_from_cache(wired):
    await server.list_submissions()
    n = len(wired.requests)
    await server.list_submissions()
    assert len(wired.requests) == n


async def test_refresh_detects_status_change(wired):
    await server.list_submissions()
    wired.confs["ConfB"][0]["StatusId"], wired.confs["ConfB"][0]["StatusName"] = 1, "Accept"
    out = await server.list_submissions(refresh=True)
    changed = [r for r in out if r["status_changed"]]
    assert [(r["submission_id"], r["status"], r["previous_status"]) for r in changed] == [(2, "Accept", 0)]


async def test_offline_status_cache(wired):
    assert await server.get_submission_status_cache() == []
    await server.list_submissions()
    wired.requests.clear()
    assert len(await server.get_submission_status_cache()) == 3
    assert len(await server.get_submission_status_cache("ConfA")) == 1
    assert wired.requests == []


async def test_inaccessible_conference_skipped_in_all_mode(wired):
    wired.forbidden.append("NoAccess")  # listed, but SubmissionAuthorViews returns 403
    out = await server.list_submissions()
    assert {r["conference"] for r in out} == {"ConfA", "ConfB"}


async def test_explicit_conference_error_is_reported(wired):
    out = await server.list_submissions("Nope")
    assert "error" in out[0]


async def test_details_and_reviews_cached(wired):
    assert (await server.get_submission("ConfA", 1))["Authors"]
    assert (await server.get_reviews("ConfA", 1))[0]["Id"] == 9
    n = len(wired.requests)
    await server.get_submission("ConfA", 1)
    await server.get_reviews("ConfA", 1)
    assert len(wired.requests) == n


async def test_tools_registered():
    names = {t.name for t in await server.mcp.list_tools()}
    assert names == {"list_my_conferences", "search_conferences", "list_submissions",
                     "get_submission_status_cache", "get_submission", "get_reviews"}
    assert not any(n.startswith(("create", "update", "delete", "submit")) for n in names)
