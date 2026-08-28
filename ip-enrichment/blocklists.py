"""
In-memory FireHOL blocklist matcher.

Loads the FireHOL `.netset` / `.ipset` files once at startup and answers
"which lists contain this IP?" in O(log n) with zero allocation on the hot
path - critical for the 200ms budget.

Implementation: every CIDR is flattened to a [start_int, end_int] interval.
Intervals for each list are sorted by start; lookup is a `bisect` + range
check. No third-party radix-tree dependency needed.
"""

from __future__ import annotations

import ipaddress
import os
from bisect import bisect_right
from pathlib import Path

from . import config as C
from ._util import log

# Some FireHOL aggregates (e.g. firehol_anonymous) carry millions of CIDRs.
# Parsing every line at startup is wasteful for a demo; cap it (still O(log n)
# at lookup time after interval-merge). Override with FIREHOL_MAX_ENTRIES=0 for
# no cap.
_MAX_ENTRIES = int(os.getenv("FIREHOL_MAX_ENTRIES", "250000"))


class _IntervalSet:
    """Sorted, non-overlapping integer intervals for one blocklist."""

    __slots__ = ("_starts", "_ends", "name", "size")

    def __init__(self, name: str):
        self.name = name
        self._starts: list[int] = []
        self._ends: list[int] = []
        self.size = 0

    @classmethod
    def from_file(cls, name: str, path: Path) -> "_IntervalSet":
        raw: list[tuple[int, int]] = []
        truncated = False
        try:
            for line in path.read_text(errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith(("#", ";")):
                    continue
                try:
                    net = ipaddress.ip_network(line, strict=False)
                except ValueError:
                    continue
                raw.append((int(net.network_address), int(net.broadcast_address)))
                if _MAX_ENTRIES and len(raw) >= _MAX_ENTRIES:
                    truncated = True
                    break
        except FileNotFoundError:
            log(f"blocklist {name}: file not found at {path} - empty set")
        if truncated:
            log(f"blocklist {name}: capped at {_MAX_ENTRIES} entries "
                f"(set FIREHOL_MAX_ENTRIES=0 to disable)")

        inst = cls(name)
        if not raw:
            return inst
        raw.sort()
        # merge overlapping / adjacent intervals
        m_start, m_end = raw[0]
        merged: list[tuple[int, int]] = []
        for s, e in raw[1:]:
            if s <= m_end + 1:
                m_end = max(m_end, e)
            else:
                merged.append((m_start, m_end))
                m_start, m_end = s, e
        merged.append((m_start, m_end))

        inst._starts = [s for s, _ in merged]
        inst._ends = [e for _, e in merged]
        inst.size = len(merged)
        return inst

    def contains(self, ip_int: int) -> bool:
        if not self._starts:
            return False
        i = bisect_right(self._starts, ip_int) - 1
        return i >= 0 and ip_int <= self._ends[i]


class BlocklistMatcher:
    """Holds every FireHOL list and reports all hits for an IP."""

    def __init__(self, sets: dict[str, _IntervalSet]):
        self._sets = sets

    @classmethod
    def load(cls, firehol_dir: Path = C.FIREHOL_DIR) -> "BlocklistMatcher":
        sets: dict[str, _IntervalSet] = {}
        for fname in C.FIREHOL_TYPE_MAP:
            path = firehol_dir / fname
            s = _IntervalSet.from_file(fname, path)
            sets[fname] = s
            log(f"blocklist {fname}: {s.size} intervals")
        return cls(sets)

    def hits(self, ip: str) -> list[str]:
        """Return the list of blocklist file names that contain `ip`."""
        try:
            ip_int = int(ipaddress.ip_address(ip))
        except ValueError:
            return []
        return [name for name, s in self._sets.items() if s.contains(ip_int)]

    def implied_type(self, hit_names: list[str]) -> str | None:
        """Most severe ip_type implied by a set of blocklist hits."""
        severity = {"tor": 3, "vpn": 2, "datacenter": 1}
        best = None
        best_rank = -1
        for name in hit_names:
            t = C.FIREHOL_TYPE_MAP.get(name)
            if t and severity.get(t, 0) > best_rank:
                best, best_rank = t, severity.get(t, 0)
        return best
