import time

from conftest import sub


def test_kv_ttl(cache):
    cache.put("k", {"a": 1})
    assert cache.get("k", ttl=60) == {"a": 1}
    assert cache.get("k", ttl=0) is None
    assert cache.get("missing", ttl=60) is None


def test_status_first_seen_not_changed(cache):
    row = cache.record_status("C", sub(1))
    assert row["changed"] is False and row["prev_status_id"] is None


def test_status_change_tracked(cache):
    cache.record_status("C", sub(1, 0, None))
    time.sleep(0.01)
    row = cache.record_status("C", sub(1, 3, "Reject"))
    assert row["changed"] is True
    assert (row["prev_status_id"], row["status_name"]) == (0, "Reject")
    assert row["last_changed"] > row["first_seen"]
    # same status again: not a change, previous status retained
    row = cache.record_status("C", sub(1, 3, "Reject"))
    assert row["changed"] is False and row["prev_status_id"] == 0


def test_cached_statuses_filter(cache):
    cache.record_status("A", sub(1))
    cache.record_status("B", sub(2))
    assert len(cache.cached_statuses()) == 2
    assert [r["conference"] for r in cache.cached_statuses("B")] == ["B"]


def test_delta_cache_levels(cache):
    cache.record_status("C", sub(1))
    assert cache.delta()["baseline_established"] is True
    cache.record_status("C", sub(1, 3, "Reject"))
    cache.record_status("C", sub(2))
    kinds = {c["row"]["submission_id"]: c["kind"] for c in cache.delta()["changes"]}
    assert kinds == {1: "status_changed", 2: "new"}
    assert cache.delta()["changes"] == []
