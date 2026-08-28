"""Tests for the IP enrichment module (Step 2.5)."""

import asyncio
import sys

sys.path.insert(0, ".")

import api._bootstrap  # noqa: F401,E402  registers `ip_enrichment`
from ip_enrichment import get_service  # noqa: E402
from ip_enrichment.blocklists import _IntervalSet  # noqa: E402
from ip_enrichment.whitelist import Whitelist  # noqa: E402


def test_interval_set_merges_and_matches(tmp_path):
    f = tmp_path / "x.netset"
    f.write_text("# comment\n10.0.0.0/24\n10.0.1.0/24\n203.0.113.0/24\n")
    s = _IntervalSet.from_file("x", f)
    assert s.size == 2  # the two /24s are adjacent -> merged
    import ipaddress
    assert s.contains(int(ipaddress.ip_address("10.0.0.55")))
    assert s.contains(int(ipaddress.ip_address("10.0.1.55")))
    assert not s.contains(int(ipaddress.ip_address("10.0.2.1")))


def test_whitelist_matches_jio_range():
    wl = Whitelist()
    m = wl.match("49.36.128.5")
    assert m is not None
    _, forced_type, min_mult = m
    assert forced_type == "residential"
    assert min_mult >= 0.9


def _enrich(ip):
    async def run():
        svc = get_service()
        await svc.startup()
        return await svc.enrich(ip)
    return asyncio.run(run())


def test_tor_exit_is_lowest_trust():
    r = _enrich("185.220.101.1")
    assert r.ip_type == "tor"
    assert r.ip_trust_multiplier == 0.30
    assert "tor_exits.ipset" in r.blocklist_hits


def test_invalid_ip_falls_back_to_unknown():
    r = _enrich("not-an-ip")
    assert r.ip_type == "unknown"
    assert r.ip_trust_multiplier == 0.8
    assert r.fallback_used is True


def test_whitelisted_indian_isp_is_trusted():
    r = _enrich("49.36.128.5")
    assert r.is_whitelisted is True
    assert r.ip_type in {"residential", "mobile_carrier"}
    assert r.ip_trust_multiplier >= 0.9


def test_result_is_cached_second_call_is_hit():
    _enrich("8.8.8.8")
    r2 = _enrich("8.8.8.8")
    assert r2.cache_hit is True
