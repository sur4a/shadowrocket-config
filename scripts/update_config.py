#!/usr/bin/env python3
"""Generate Shadowrocket russia.config from template and opencck IP list."""

from __future__ import annotations

import argparse
import ipaddress
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

MARKER = "# IP ranges - direct (fix 1: no no-resolve)"
END_MARKER = "# Final"
SOURCE_URL = "https://russia.iplist.opencck.org/?format=text&data=cidr4"
USER_AGENT = "shadowrocket-config-updater/1.0"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = REPO_ROOT / "russia.config.template"
DEFAULT_OUTPUT = REPO_ROOT / "russia.config"


def fetch_cidrs(url: str) -> list[str]:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=120) as response:
            text = response.read().decode("utf-8")
    except URLError as exc:
        raise SystemExit(f"Failed to fetch CIDR list: {exc}") from exc

    cidrs: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            ipaddress.ip_network(line, strict=False)
        except ValueError as exc:
            raise SystemExit(f"Invalid CIDR from source: {line!r} ({exc})") from exc
        cidrs.append(line)

    if not cidrs:
        raise SystemExit("No CIDR entries received from source")

    return sorted(set(cidrs), key=_sort_key)


def _sort_key(cidr: str) -> tuple[int, int]:
    network = ipaddress.ip_network(cidr, strict=False)
    return int(network.network_address), network.prefixlen


def build_rules(cidrs: list[str]) -> str:
    lines = [MARKER]
    lines.extend(f"IP-CIDR,{cidr},DIRECT" for cidr in cidrs)
    return "\n".join(lines)


def build_config(template: str, cidrs: list[str]) -> str:
    marker_pos = template.find(MARKER)
    if marker_pos == -1:
        raise SystemExit(f"Marker not found in template: {MARKER!r}")

    end_pos = template.find(END_MARKER, marker_pos)
    if end_pos == -1:
        raise SystemExit(f"End marker not found in template: {END_MARKER!r}")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    content = re.sub(
        r"^# Shadowrocket: .*$",
        f"# Shadowrocket: {timestamp}",
        template,
        count=1,
        flags=re.MULTILINE,
    )

    marker_pos = content.find(MARKER)
    end_pos = content.find(END_MARKER, marker_pos)
    new_rules = build_rules(cidrs)

    return content[:marker_pos] + new_rules + "\n\n" + content[end_pos:]


def extract_ip_rules(content: str) -> str:
    marker_pos = content.find(MARKER)
    if marker_pos == -1:
        raise SystemExit(f"Marker not found: {MARKER!r}")
    end_pos = content.find(END_MARKER, marker_pos)
    if end_pos == -1:
        raise SystemExit(f"End marker not found: {END_MARKER!r}")
    return content[marker_pos:end_pos]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate russia.config from template and opencck IP list",
    )
    parser.add_argument(
        "-t",
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE,
        help="Template config (default: russia.config.template)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output config file (default: russia.config)",
    )
    parser.add_argument(
        "-u",
        "--url",
        default=SOURCE_URL,
        help="opencck CIDR export URL",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and validate without writing the output file",
    )
    args = parser.parse_args()

    if not args.template.is_file():
        raise SystemExit(f"Template not found: {args.template}")

    cidrs = fetch_cidrs(args.url)
    print(f"Fetched {len(cidrs)} unique CIDR entries")

    template = args.template.read_text(encoding="utf-8")
    new_content = build_config(template, cidrs)

    if args.dry_run:
        print("Dry run: output file was not written")
        return 0

    new_rules = extract_ip_rules(new_content)
    if args.output.is_file():
        existing_rules = extract_ip_rules(args.output.read_text(encoding="utf-8"))
        if existing_rules == new_rules:
            print(f"No changes needed: {args.output}")
            return 0

    args.output.write_text(new_content, encoding="utf-8")
    print(f"Created {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
