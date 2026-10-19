#!/usr/bin/env python3
"""Build languages.csv skeleton from Glottolog (CC-BY). Needs internet; run on your machine, not in CI.

Glottolog publishes its data as a CLDF dataset (glottolog/glottolog-cldf on GitHub / Zenodo). This script downloads
the languages table and the AES endangerment values, filters to the endangered set, and writes
app/data/seed/languages.csv with the columns the agent expects. Speaker counts, ages and transmission are NOT in
Glottolog: they stay empty here and are filled from UNESCO WAL / fieldwork (see seed/README.md).

Usage: python app/data/fetch_glottolog.py [--release v5.1] [--out app/data/seed/languages.csv] [--min-status severely]
"""
from __future__ import annotations
import argparse, csv, io, sys, zipfile
import httpx

RELEASES = "https://api.github.com/repos/glottolog/glottolog-cldf/releases"
# AES (Agglomerated Endangerment Status) codes used in the CLDF values table → our four buckets
AES_MAP = {"not_endangered": None, "threatened": "vulnerable", "shifting": "definitely",
           "moribund": "severely", "nearly_extinct": "critically", "extinct": None}
ORDER = ["vulnerable", "definitely", "severely", "critically"]


def latest_zip_url(release: str | None) -> str:
    rel = httpx.get(RELEASES, timeout=60, follow_redirects=True).json()
    chosen = next((r for r in rel if release is None or r["tag_name"] == release), rel[0])
    return chosen["zipball_url"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--release", default=None)
    ap.add_argument("--out", default="app/data/seed/languages.csv")
    ap.add_argument("--min-status", default="definitely", choices=ORDER)
    a = ap.parse_args()
    url = latest_zip_url(a.release)
    print("downloading", url, file=sys.stderr)
    blob = httpx.get(url, timeout=600, follow_redirects=True).content
    z = zipfile.ZipFile(io.BytesIO(blob))
    lang_path = next(n for n in z.namelist() if n.endswith("cldf/languages.csv"))
    val_path = next(n for n in z.namelist() if n.endswith("cldf/values.csv"))
    langs = list(csv.DictReader(io.TextIOWrapper(z.open(lang_path), encoding="utf-8")))
    aes: dict[str, str] = {}
    for row in csv.DictReader(io.TextIOWrapper(z.open(val_path), encoding="utf-8")):
        if row.get("Parameter_ID") == "aes":
            aes[row["Language_ID"]] = row.get("Code_ID", "").split("-")[-1]
    keep_from = ORDER.index(a.min_status)
    out = []
    for l in langs:
        if l.get("Level") != "language":
            continue
        bucket = AES_MAP.get(aes.get(l["ID"], ""), None)
        if bucket is None or ORDER.index(bucket) < keep_from:
            continue
        out.append({"glottocode": l["ID"], "name": l["Name"], "family": l.get("Family_ID", ""), "country": l.get("Countries", "").split(";")[0],
                    "region": l.get("Macroarea", ""), "lat": l.get("Latitude", ""), "lon": l.get("Longitude", ""),
                    "speakers": "", "speakers_year": "", "median_speaker_age": "", "endangerment": bucket, "intergenerational_transmission": ""})
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader(); w.writerows(out)
    print(f"wrote {len(out)} languages to {a.out} (speakers/age columns empty: fill from UNESCO WAL / fieldwork)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
