"""Fetch a real corpus from OpenAlex into the Lazarus seed schema.

    python app/data/fetch_openalex.py --query "slip detection tactile manipulation" --field robotics --parent engineering \
        --query "stick-slip friction precursor acoustic emission" --field seismology --parent earth_science \
        --per-query 150 --mailto you@example.org --out app/data/seed

Each --query/--field/--parent triple pulls up to --per-query works (with abstracts) and tags them with that field.
Writes papers.csv, paper_entities.csv, citations.csv, fields.csv, entity_kinds.csv (kinds default to 'object';
see the note at the end) and leaves problems.csv / problem_entities.csv for you to author.

OpenAlex: https://docs.openalex.org — free, no key; pass mailto for the polite pool. Abstracts come as an inverted
index and are rebuilt here. Entities = OpenAlex concepts (display_name, level ≥ 1) plus keywords.
Needs internet; the hackathon container cannot reach openalex.org, run it on a laptop or servingz.
"""
from __future__ import annotations
import argparse, csv, os, time
import httpx

API = "https://api.openalex.org/works"


def rebuild_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    pos = {}
    for word, idxs in inv.items():
        for i in idxs:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


def fetch(query: str, n: int, mailto: str) -> list[dict]:
    out, cursor = [], "*"
    with httpx.Client(timeout=60) as cli:
        while len(out) < n and cursor:
            r = cli.get(API, params={"search": query, "per-page": min(200, n - len(out)), "cursor": cursor, "mailto": mailto,
                                     "select": "id,title,publication_year,cited_by_count,abstract_inverted_index,concepts,keywords,referenced_works"})
            r.raise_for_status()
            js = r.json()
            out.extend(js["results"])
            cursor = js.get("meta", {}).get("next_cursor")
            time.sleep(0.2)
    return out[:n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", action="append", required=True)
    ap.add_argument("--field", action="append", required=True)
    ap.add_argument("--parent", action="append", required=True)
    ap.add_argument("--per-query", type=int, default=100)
    ap.add_argument("--mailto", required=True)
    ap.add_argument("--out", default="app/data/seed")
    a = ap.parse_args()
    assert len(a.query) == len(a.field) == len(a.parent), "give --query/--field/--parent in triples"
    os.makedirs(a.out, exist_ok=True)

    papers, ents, cites, fields, allents = [], [], [], {}, set()
    seen = set()
    for query, field, parent in zip(a.query, a.field, a.parent):
        fields[field] = parent
        for w in fetch(query, a.per_query, a.mailto):
            pid = w["id"].rsplit("/", 1)[-1]
            if pid in seen:
                continue
            seen.add(pid)
            concepts = [c["display_name"].lower() for c in w.get("concepts", []) if c.get("level", 0) >= 1 and c.get("score", 0) > 0.3]
            keywords = [k["display_name"].lower() for k in (w.get("keywords") or []) if k.get("display_name")]
            entities = sorted(set(concepts + keywords))
            allents.update(entities)
            papers.append([pid, w.get("title") or "", field, w.get("publication_year") or 0, w.get("cited_by_count") or 0,
                           ";".join(entities), rebuild_abstract(w.get("abstract_inverted_index"))[:2000]])
            ents.extend([[pid, e] for e in entities])
            cites.extend([[pid, ref.rsplit("/", 1)[-1]] for ref in (w.get("referenced_works") or [])])
    # keep only citations whose target is in the corpus (others cannot be joined anyway)
    ids = {p[0] for p in papers}
    cites = [c for c in cites if c[1] in ids]

    def write(name, header, rows):
        with open(os.path.join(a.out, name), "w", newline="") as f:
            wr = csv.writer(f); wr.writerow(header); wr.writerows(rows)

    write("papers.csv", ["paper_id", "title", "field", "year", "cited_by_count", "entities", "abstract"], papers)
    write("paper_entities.csv", ["paper_id", "entity"], ents)
    write("citations.csv", ["citing_id", "cited_id"], cites)
    write("fields.csv", ["field", "parent_field"], [[k, v] for k, v in fields.items()])
    # Entity kinds: OpenAlex concepts are topics, not method/mechanism labels. Default everything to 'object' so the
    # Skeptic REJECTS until a human (or a day-2 classifier) marks methods and mechanisms. Honest by default.
    write("entity_kinds.csv", ["entity", "kind"], [[e, "object"] for e in sorted(allents)])
    print(f"{len(papers)} papers, {len(ents)} entity rows, {len(cites)} in-corpus citations, {len(allents)} entities → {a.out}")
    print("Next: author problems.csv + problem_entities.csv, and classify entity_kinds.csv (method | mechanism | object | generic).")


if __name__ == "__main__":
    main()
