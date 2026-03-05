#!/usr/bin/env python3
"""Patch systemdata.json with region_id per system and create regions.json.

Downloads the EVE SDE JSONL zip, extracts regionID from mapSolarSystems.jsonl,
region names from mapRegions.jsonl, then:
  1. Adds "region_id" to each system entry in systemdata.json
  2. Creates taco/resources/data/regions.json  (region_id -> region_name)

Usage:
    python -m taco.tools.patch_regions
"""

import io
import json
import os
import sys
import urllib.request
import zipfile

SDE_URL = "https://developers.eveonline.com/static-data/eve-online-static-data-latest-jsonl.zip"


def download_sde() -> bytes:
    print(f"Downloading SDE zip from {SDE_URL} ...")
    with urllib.request.urlopen(SDE_URL) as resp:
        data = resp.read()
    print(f"  Downloaded {len(data) / 1024 / 1024:.1f} MB")
    return data


def extract_system_regions(zf: zipfile.ZipFile) -> dict[int, int]:
    """Extract native_system_id -> region_id from mapSolarSystems.jsonl."""
    target = None
    for name in zf.namelist():
        if name.endswith("mapSolarSystems.jsonl"):
            target = name
            break
    if target is None:
        raise RuntimeError("mapSolarSystems.jsonl not found in SDE zip")

    system_regions: dict[int, int] = {}
    with zf.open(target) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            sys_id = record.get("_key") or record.get("solarSystemID")
            region_id = record.get("regionID", 0)
            if sys_id and region_id:
                system_regions[int(sys_id)] = int(region_id)

    print(f"  Extracted regionID for {len(system_regions)} systems")
    return system_regions


def extract_region_names(zf: zipfile.ZipFile) -> dict[int, str]:
    """Extract region_id -> region_name from mapRegions.jsonl."""
    target = None
    for name in zf.namelist():
        if name.endswith("mapRegions.jsonl"):
            target = name
            break
    if target is None:
        raise RuntimeError("mapRegions.jsonl not found in SDE zip")

    region_names: dict[int, str] = {}
    with zf.open(target) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            region_id = record.get("_key") or record.get("regionID")
            # Region names are in a nested "name" dict with language keys
            name_field = record.get("name")
            if isinstance(name_field, dict):
                name = name_field.get("en", "")
            elif isinstance(name_field, str):
                name = name_field
            else:
                name = ""
            if region_id and name:
                region_names[int(region_id)] = name

    print(f"  Extracted names for {len(region_names)} regions")
    return region_names


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.normpath(os.path.join(script_dir, "..", "resources", "data"))

    systemdata_path = os.path.join(data_dir, "systemdata.json")
    regions_path = os.path.join(data_dir, "regions.json")

    if not os.path.exists(systemdata_path):
        print(f"Error: {systemdata_path} not found")
        sys.exit(1)

    # Download and parse SDE
    sde_data = download_sde()
    with zipfile.ZipFile(io.BytesIO(sde_data)) as zf:
        system_regions = extract_system_regions(zf)
        region_names = extract_region_names(zf)

    # Load existing systemdata.json
    print(f"Loading {systemdata_path} ...")
    with open(systemdata_path, "r") as f:
        systems = json.load(f)
    print(f"  Loaded {len(systems)} systems")

    # Patch each system with region_id
    patched = 0
    used_regions = set()
    for entry in systems:
        native_id = entry["native_id"]
        rid = system_regions.get(native_id, 0)
        entry["region_id"] = rid
        if rid:
            patched += 1
            used_regions.add(rid)

    print(f"  Patched {patched} systems with region_id ({len(used_regions)} unique regions)")

    # Write patched systemdata.json
    with open(systemdata_path, "w") as f:
        json.dump(systems, f, indent=1)
    print(f"  Written {systemdata_path}")

    # Build and write regions.json (only regions that have systems)
    regions_output = {str(rid): region_names[rid] for rid in used_regions if rid in region_names}
    with open(regions_path, "w") as f:
        json.dump(regions_output, f, indent=1)
    print(f"  Written {regions_path} ({len(regions_output)} regions)")

    print("\nDone!")


if __name__ == "__main__":
    main()
