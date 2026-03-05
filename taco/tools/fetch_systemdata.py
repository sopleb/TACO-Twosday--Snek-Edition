#!/usr/bin/env python3
"""Fetch fresh solar system data from CCP's ESI API and write systemdata.json.

Usage:
    pip install aiohttp
    python -m taco.tools.fetch_systemdata [--output PATH]

Defaults output to taco/resources/data/systemdata.json

This replaces the static protobuf-derived snapshot with live data from ESI,
ensuring new/changed systems are included.  Total: ~19k requests, takes 5-15 min.

Also downloads the SDE (Static Data Export) to extract 2D schematic map
positions (position2D) used by EVE's in-game 2D map.
"""

import argparse
import asyncio
import io
import json
import os
import re
import sys
import time
import zipfile


BASE_URL = "https://esi.evetech.net/latest"
MAX_CONCURRENT = 20
MAX_RETRIES = 5
RATE_LIMIT_FLOOR = 10  # pause when X-Ratelimit-Remaining drops below this


async def fetch_json(session, url: str, semaphore: asyncio.Semaphore,
                     label: str = "") -> dict | list | None:
    """GET a single ESI endpoint with retry/backoff and rate-limit awareness."""
    for attempt in range(MAX_RETRIES):
        async with semaphore:
            try:
                async with session.get(url) as resp:
                    # Rate-limit awareness
                    remaining = resp.headers.get("X-Esi-Error-Limit-Remain")
                    if remaining is not None and int(remaining) < RATE_LIMIT_FLOOR:
                        reset = int(resp.headers.get("X-Esi-Error-Limit-Reset", 5))
                        print(f"\n  Rate limit low ({remaining} remaining), "
                              f"pausing {reset}s...")
                        await asyncio.sleep(reset)

                    if resp.status == 200:
                        return await resp.json()

                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", 5))
                        wait = retry_after * (2 ** attempt)
                        print(f"\n  429 rate limited on {label or url}, "
                              f"waiting {wait}s (attempt {attempt + 1})...")
                        await asyncio.sleep(wait)
                        continue

                    if resp.status in (502, 503, 504):
                        wait = 2 ** attempt
                        print(f"\n  {resp.status} on {label or url}, "
                              f"retrying in {wait}s (attempt {attempt + 1})...")
                        await asyncio.sleep(wait)
                        continue

                    print(f"\n  Unexpected {resp.status} on {label or url}")
                    return None

            except (asyncio.TimeoutError, Exception) as e:
                wait = 2 ** attempt
                if attempt < MAX_RETRIES - 1:
                    print(f"\n  Error on {label or url}: {e}, "
                          f"retrying in {wait}s...")
                    await asyncio.sleep(wait)
                else:
                    print(f"\n  Failed after {MAX_RETRIES} attempts: "
                          f"{label or url}: {e}")
                    return None

    return None


async def fetch_all_system_ids(session, semaphore) -> list[int]:
    """Fetch the list of all k-space solar system IDs from ESI.

    Excludes wormhole (31xxxxxx) and abyssal (32xxxxxx+) systems — only
    returns known-space systems (30000000–30999999).
    """
    print("Fetching system ID list...")
    result = await fetch_json(session, f"{BASE_URL}/universe/systems/",
                              semaphore, "system list")
    if result is None:
        raise RuntimeError("Failed to fetch system ID list")
    kspace = [s for s in result if 30000000 <= s < 31000000]
    print(f"  Got {len(result)} total, keeping {len(kspace)} k-space systems "
          f"(excluded {len(result) - len(kspace)} wormhole/abyssal)")
    return kspace


async def fetch_constellation_regions(session, semaphore) -> dict[int, int]:
    """Build constellation_id -> region_id mapping via region endpoints."""
    print("Fetching region list...")
    region_ids = await fetch_json(session, f"{BASE_URL}/universe/regions/",
                                  semaphore, "region list")
    if region_ids is None:
        raise RuntimeError("Failed to fetch region list")
    print(f"  Got {len(region_ids)} regions, fetching details...")

    constellation_to_region: dict[int, int] = {}
    done = 0

    async def fetch_region(region_id):
        nonlocal done
        data = await fetch_json(
            session,
            f"{BASE_URL}/universe/regions/{region_id}/",
            semaphore,
            f"region {region_id}",
        )
        if data and "constellations" in data:
            for c_id in data["constellations"]:
                constellation_to_region[c_id] = region_id
        done += 1
        print(f"\r  Regions: {done}/{len(region_ids)}", end="", flush=True)

    await asyncio.gather(*[fetch_region(rid) for rid in region_ids])
    print(f"\n  Mapped {len(constellation_to_region)} constellations to regions")
    return constellation_to_region


async def fetch_systems(session, system_ids: list[int],
                        semaphore) -> list[dict]:
    """Fetch details for all systems concurrently."""
    print(f"Fetching {len(system_ids)} system details...")
    results: list[dict | None] = [None] * len(system_ids)
    done = 0

    async def fetch_one(idx, sys_id):
        nonlocal done
        data = await fetch_json(
            session,
            f"{BASE_URL}/universe/systems/{sys_id}/",
            semaphore,
            f"system {sys_id}",
        )
        results[idx] = data
        done += 1
        if done % 100 == 0 or done == len(system_ids):
            print(f"\r  Systems: {done}/{len(system_ids)}", end="", flush=True)

    await asyncio.gather(*[fetch_one(i, sid)
                           for i, sid in enumerate(system_ids)])
    print()

    # Filter out failures
    valid = [r for r in results if r is not None]
    if len(valid) < len(system_ids):
        print(f"  Warning: {len(system_ids) - len(valid)} systems failed to fetch")
    return valid


async def fetch_stargates(session, stargate_ids: list[int],
                          semaphore) -> dict[int, int]:
    """Fetch stargate details, return stargate_id -> destination_system_id."""
    print(f"Fetching {len(stargate_ids)} stargate details...")
    gate_to_dest: dict[int, int] = {}
    done = 0

    async def fetch_one(gate_id):
        nonlocal done
        data = await fetch_json(
            session,
            f"{BASE_URL}/universe/stargates/{gate_id}/",
            semaphore,
            f"stargate {gate_id}",
        )
        if data and "destination" in data:
            gate_to_dest[gate_id] = data["destination"]["system_id"]
        done += 1
        if done % 200 == 0 or done == len(stargate_ids):
            print(f"\r  Stargates: {done}/{len(stargate_ids)}",
                  end="", flush=True)

    await asyncio.gather(*[fetch_one(gid) for gid in stargate_ids])
    print()
    return gate_to_dest


async def fetch_sde_positions(session, semaphore,
                             sde_url: str | None = None) -> dict[int, tuple[float, float]]:
    """Download the SDE JSONL zip and extract position2D for each solar system.

    Returns native_id -> (x2d, y2d) in map units (divided by 1e14).
    """
    positions: dict[int, tuple[float, float]] = {}

    if sde_url is None:
        sde_url = "https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip"

    print(f"Downloading SDE zip...")
    try:
        async with semaphore:
            async with session.get(sde_url) as resp:
                if resp.status != 200:
                    print(f"  Warning: SDE download failed (HTTP {resp.status})")
                    return positions

                data = await resp.read()
                print(f"  Downloaded {len(data) / 1024 / 1024:.1f} MB")
    except Exception as e:
        print(f"  Warning: SDE download failed: {e}")
        return positions

    # Extract mapSolarSystems.jsonl from the zip
    print("Extracting position2D from SDE...")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # Find the mapSolarSystems file (might be in a subdirectory)
            target = None
            for name in zf.namelist():
                if name.endswith("mapSolarSystems.jsonl"):
                    target = name
                    break
            if target is None:
                print("  Warning: mapSolarSystems.jsonl not found in SDE zip")
                return positions

            with zf.open(target) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    record = json.loads(line)
                    # _key is the solarSystemID in JSONL format
                    sys_id = record.get("_key") or record.get("solarSystemID")
                    pos2d = record.get("position2D")
                    if sys_id and pos2d:
                        # position2D has x and y fields (no z)
                        x2d = pos2d.get("x", 0.0) / 1e14
                        y2d = pos2d.get("y", 0.0) / 1e14
                        positions[int(sys_id)] = (x2d, y2d)

    except Exception as e:
        print(f"  Warning: Failed to parse SDE: {e}")
        return positions

    print(f"  Extracted 2D positions for {len(positions)} systems")
    return positions


def build_systemdata(systems: list[dict], stargates: dict[int, int],
                     constellation_regions: dict[int, int],
                     sde_positions: dict[int, tuple[float, float]] | None = None) -> list[dict]:
    """Transform raw ESI data into the app's systemdata.json format."""
    # Sort by native_id for stable ordering
    systems.sort(key=lambda s: s["system_id"])

    # Build native_id -> sequential internal id
    native_to_internal: dict[int, int] = {}
    for idx, sys_data in enumerate(systems):
        native_to_internal[sys_data["system_id"]] = idx

    # Build system_id -> constellation_id for region lookups
    system_constellation: dict[int, int] = {}
    for sys_data in systems:
        system_constellation[sys_data["system_id"]] = sys_data.get(
            "constellation_id", 0)

    # Build system_id -> set of connected system_ids from stargates
    connections: dict[int, set[int]] = {}
    for sys_data in systems:
        sys_id = sys_data["system_id"]
        connections[sys_id] = set()
        for gate_id in sys_data.get("stargates", []):
            dest_sys = stargates.get(gate_id)
            if dest_sys is not None:
                connections[sys_id].add(dest_sys)

    # Build output
    output = []
    for idx, sys_data in enumerate(systems):
        sys_id = sys_data["system_id"]
        pos = sys_data.get("position", {})

        # Coordinate transform: ESI meters -> map units
        # map_x = esi_x / 1e14, map_y = esi_z / 1e14, map_z = 0.0
        map_x = pos.get("x", 0.0) / 1e14
        map_y = pos.get("z", 0.0) / 1e14
        map_z = 0.0

        # Build connected_to array
        sys_constellation = system_constellation.get(sys_id, 0)
        sys_region = constellation_regions.get(sys_constellation, 0)

        connected_to = []
        for dest_id in sorted(connections.get(sys_id, [])):
            if dest_id not in native_to_internal:
                continue
            dest_constellation = system_constellation.get(dest_id, 0)
            dest_region = constellation_regions.get(dest_constellation, 0)
            is_regional = (sys_region != dest_region and
                           sys_region != 0 and dest_region != 0)

            connected_to.append({
                "to_system_id": native_to_internal[dest_id],
                "to_system_native_id": dest_id,
                "is_regional": is_regional,
            })

        # 2D schematic coords from SDE (fall back to 3D projection if absent)
        if sde_positions and sys_id in sde_positions:
            x2d, y2d = sde_positions[sys_id]
        else:
            x2d, y2d = map_x, map_y

        # Region ID for this system (via constellation -> region mapping)
        region_id = constellation_regions.get(sys_constellation, 0)

        output.append({
            "id": idx,
            "native_id": sys_id,
            "name": sys_data.get("name", ""),
            "x": map_x,
            "y": map_y,
            "z": map_z,
            "x2d": x2d,
            "y2d": y2d,
            "region_id": region_id,
            "connected_to": connected_to,
        })

    return output


async def main():
    parser = argparse.ArgumentParser(
        description="Fetch EVE Online system data from ESI")
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output path (default: taco/resources/data/systemdata.json)",
    )
    parser.add_argument(
        "--sde-url",
        default=None,
        help="Direct URL to the SDE JSONL zip (auto-discovered if omitted)",
    )
    args = parser.parse_args()

    if args.output is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(
            script_dir, "..", "resources", "data", "systemdata.json")
    else:
        output_path = args.output
    output_path = os.path.normpath(output_path)

    try:
        import aiohttp
    except ImportError:
        print("Error: aiohttp is required. Install it with:")
        print("  pip install aiohttp")
        sys.exit(1)

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT, limit_per_host=MAX_CONCURRENT)

    start_time = time.time()
    print("=== ESI System Data Fetcher ===\n")

    async with aiohttp.ClientSession(timeout=timeout,
                                     connector=connector) as session:
        # Step 1: Get all system IDs
        system_ids = await fetch_all_system_ids(session, semaphore)

        # Step 2: Build constellation -> region mapping
        constellation_regions = await fetch_constellation_regions(
            session, semaphore)

        # Step 3: Fetch all system details
        systems = await fetch_systems(session, system_ids, semaphore)

        # Step 4: Collect all stargate IDs and fetch their destinations
        all_gate_ids = set()
        for sys_data in systems:
            for gate_id in sys_data.get("stargates", []):
                all_gate_ids.add(gate_id)
        print(f"Found {len(all_gate_ids)} unique stargates")

        stargates = await fetch_stargates(
            session, sorted(all_gate_ids), semaphore)

        # Step 5: Fetch SDE 2D schematic positions
        sde_positions = await fetch_sde_positions(
            session, semaphore, sde_url=args.sde_url)

    # Step 6: Build and write output
    print("\nBuilding system data...")
    output = build_systemdata(systems, stargates, constellation_regions,
                              sde_positions=sde_positions)

    # Stats
    total_connections = sum(len(s["connected_to"]) for s in output)
    regional = sum(1 for s in output
                   for c in s["connected_to"] if c["is_regional"])
    no_connections = sum(1 for s in output if not s["connected_to"])
    has_2d = sum(1 for s in output if s.get("x2d") != s.get("x") or s.get("y2d") != s.get("y"))

    print(f"\nWriting {len(output)} systems to {output_path}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=1)

    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.0f}s")
    print(f"  Systems:     {len(output)}")
    print(f"  Connections: {total_connections} "
          f"({regional} regional)")
    print(f"  No gates:    {no_connections} "
          f"(wormhole/special systems)")
    print(f"  2D coords:   {has_2d} systems with SDE schematic positions")


if __name__ == "__main__":
    asyncio.run(main())
