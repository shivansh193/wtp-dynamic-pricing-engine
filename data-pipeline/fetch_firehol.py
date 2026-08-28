"""
Step 2 - Firehol VPN / datacenter / Tor blocklists.

Downloads the following ipsets from the firehol/blocklist-ipsets repo
(raw.githubusercontent.com) into data/raw/firehol/:

  - firehol_level1.netset   (spam / hijacked / bogon aggregate)
  - datacenters.netset      (hosting / cloud ranges)
  - vpn.netset              (known commercial VPN egress)
  - tor_exits.ipset         (Tor exit nodes)

If the network is unavailable, a small but real sample of well-known ranges is
written for each list so the IP-enrichment module still loads and classifies.
The `.source.json` sidecar records which lists are live vs sample.
"""

from __future__ import annotations

import config as C
from _util import http_get, log, write_source_sidecar

OUT_DIR = C.RAW_DIR / "firehol"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Minimal real-world fallbacks (CIDR) so classification still works offline.
FALLBACK_SAMPLES = {
    "firehol_level1.netset": [
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
        "169.254.0.0/16", "172.16.0.0/12", "192.0.2.0/24", "192.168.0.0/16",
        "198.18.0.0/15", "203.0.113.0/24", "224.0.0.0/3",
    ],
    "datacenters.netset": [
        # AWS, GCP, Azure, DigitalOcean, OVH, Hetzner, Linode sample blocks
        "3.0.0.0/9", "13.32.0.0/15", "15.177.0.0/18", "18.130.0.0/16",
        "34.64.0.0/10", "35.184.0.0/13", "52.0.0.0/11", "104.16.0.0/13",
        "128.199.0.0/16", "134.209.0.0/16", "138.197.0.0/16", "142.250.0.0/15",
        "157.90.0.0/16", "159.65.0.0/16", "167.71.0.0/16", "172.104.0.0/15",
        "178.62.0.0/16", "188.166.0.0/17", "195.201.0.0/16", "207.154.192.0/18",
    ],
    "vpn.netset": [
        # NordVPN / ExpressVPN / Surfshark / PIA / Mullvad sample egress blocks
        "45.83.88.0/22", "89.238.128.0/18", "138.199.0.0/16", "143.244.32.0/19",
        "146.70.0.0/16", "154.6.0.0/16", "169.150.192.0/18", "185.65.134.0/23",
        "185.159.156.0/22", "193.9.113.0/24", "196.240.54.0/23", "212.102.32.0/19",
    ],
    "tor_exits.ipset": [
        "23.129.64.0/24", "45.66.33.0/24", "51.75.64.0/24", "77.247.181.0/24",
        "104.244.72.0/21", "171.25.193.0/24", "185.220.100.0/22", "199.87.154.0/24",
    ],
}


def main() -> None:
    log("Fetching Firehol blocklists...")
    provenance = {}
    for fname, urls in C.FIREHOL_LISTS.items():
        target = OUT_DIR / fname
        resp = None
        used_url = None
        for url in urls:
            resp = http_get(url, timeout=30)
            if resp is not None and resp.text.strip():
                used_url = url
                break
        if resp is not None and resp.text.strip():
            target.write_text(resp.text)
            is_exact = used_url == urls[0]
            provenance[fname] = "live" if is_exact else f"live-alt({used_url.rsplit('/', 1)[-1]})"
            n = sum(1 for ln in resp.text.splitlines() if ln and not ln.startswith("#"))
            log(f"  {fname}: {provenance[fname]}, {n} entries")
        else:
            lines = [
                f"# FALLBACK SAMPLE for {fname} - network fetch failed",
                f"# tried: {', '.join(urls)}",
                *FALLBACK_SAMPLES[fname],
            ]
            target.write_text("\n".join(lines) + "\n")
            provenance[fname] = "sample_fallback"
            log(f"  {fname}: FALLBACK sample, {len(FALLBACK_SAMPLES[fname])} entries")

    # one sidecar for the whole directory
    marker = OUT_DIR / "firehol.csv"  # sidecar helper keys off a file path
    marker.write_text("list,status\n" + "\n".join(f"{k},{v}" for k, v in provenance.items()) + "\n")
    all_live = all(v == "live" for v in provenance.values())
    write_source_sidecar(
        marker,
        source="github.com/firehol/blocklist-ipsets (raw.githubusercontent.com)",
        live=all_live,
        note="per-list status: " + ", ".join(f"{k}={v}" for k, v in provenance.items()),
    )


if __name__ == "__main__":
    main()
