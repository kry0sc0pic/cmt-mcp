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


async def test_list_is_compact(wired):
    out = await server.list_submissions()
    assert all("abstract" not in r and "files" not in r for r in out)


async def test_delta_first_call_sets_baseline(wired):
    d = await server.get_delta()
    assert d["baseline_established"] is True and d["changes"] == []
    d = await server.get_delta()
    assert d["baseline_established"] is False and d["changes"] == []


async def test_delta_reports_status_change_once(wired):
    await server.get_delta()
    wired.confs["ConfB"][0]["StatusId"], wired.confs["ConfB"][0]["StatusName"] = 1, "Accept"
    d = await server.get_delta()
    assert [(c["submission_id"], c["change"], c["status"], c["previous_status"]) for c in d["changes"]] == \
        [(2, "status_changed", "Accept", "Pending")]
    assert (await server.get_delta())["changes"] == []  # acknowledged


async def test_delta_not_consumed_by_list_submissions(wired):
    await server.get_delta()
    wired.confs["ConfB"][0]["StatusId"], wired.confs["ConfB"][0]["StatusName"] = 1, "Accept"
    await server.list_submissions(refresh=True)  # updates cache but must not ack
    assert len((await server.get_delta())["changes"]) == 1


async def test_delta_peek_does_not_acknowledge(wired):
    await server.get_delta()
    wired.confs["ConfA"][0]["NumberOfReviews"] = 3
    assert [c["change"] for c in (await server.get_delta(acknowledge=False))["changes"]] == ["new_reviews"]
    assert [c["change"] for c in (await server.get_delta())["changes"]] == ["new_reviews"]
    assert (await server.get_delta())["changes"] == []


async def test_delta_new_submission_and_conference_scope(wired):
    await server.get_delta()
    wired.confs["ConfB"].append({**wired.confs["ConfB"][0], "Id": 99, "Title": "Brand new"})
    d = await server.get_delta("ConfA")
    assert d["changes"] == []  # scoped away from ConfB
    d = await server.get_delta()
    assert [(c["submission_id"], c["change"]) for c in d["changes"]] == [(99, "new")]


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
                     "get_delta", "get_submission", "get_reviews"}
    assert not any(n.startswith(("create", "update", "delete", "submit")) for n in names)
