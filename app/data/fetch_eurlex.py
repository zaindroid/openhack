"""Fetch EU legal acts for a policy area from EUR-Lex and write a laws.csv skeleton (features left for review).

EUR-Lex offers a public SPARQL endpoint over the CELLAR repository (no key):
    https://publications.europa.eu/webapi/rdf/sparql
Acts are filtered by EuroVoc subject (--eurovoc) and/or a title keyword (--keyword). The instrument type is inferred
from the act type (regulation/directive → mandate; decision on funding → subsidy) and should be reviewed by a human.
The ';'-separated `features` column is left EMPTY on purpose: feature tagging needs the text of the act. The day-2 job
is to run the act text through the model with the features_dict vocabulary and store the result flagged as model output.

Usage (needs internet; run on your machine, not in a sandbox):
    python app/data/fetch_eurlex.py --eurovoc "energy saving" --keyword "building" --since 2010 --out app/data/raw/laws_eu.csv
"""
from __future__ import annotations
import argparse, csv, os, sys
import httpx

SPARQL = "https://publications.europa.eu/webapi/rdf/sparql"

QUERY = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT DISTINCT ?celex ?title ?date ?type WHERE {
  ?act cdm:resource_legal_id_celex ?celex ;
       cdm:work_date_document ?date ;
       cdm:work_has_resource-type ?rt .
  ?rt skos:prefLabel ?type . FILTER(lang(?type) = "en")
  ?exp cdm:expression_belongs_to_work ?act ; cdm:expression_title ?title ; cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> .
  %EUROVOC%
  FILTER(CONTAINS(LCASE(STR(?title)), LCASE("%KEYWORD%")))
  FILTER(?date >= "%SINCE%-01-01"^^<http://www.w3.org/2001/XMLSchema#date>)
} ORDER BY DESC(?date) LIMIT %LIMIT%
"""

EUROVOC_CLAUSE = """
  ?act cdm:work_is_about_concept_eurovoc ?ev . ?ev skos:prefLabel ?evl . FILTER(lang(?evl) = "en" && LCASE(STR(?evl)) = LCASE("%EUROVOC%"))
"""


def infer_instrument(act_type: str) -> str:
    t = act_type.lower()
    if "directive" in t or "regulation" in t:
        return "mandate"
    if "decision" in t and "financ" in t:
        return "subsidy"
    return "mandate"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--eurovoc", default="")
    ap.add_argument("--keyword", required=True)
    ap.add_argument("--policy-area", default="")
    ap.add_argument("--since", type=int, default=2010)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out", default="app/data/raw/laws_eu.csv")
    a = ap.parse_args()
    q = QUERY.replace("%KEYWORD%", a.keyword).replace("%SINCE%", str(a.since)).replace("%LIMIT%", str(a.limit))
    q = q.replace("%EUROVOC%", EUROVOC_CLAUSE.replace("%EUROVOC%", a.eurovoc) if a.eurovoc else "")
    r = httpx.get(SPARQL, params={"query": q, "format": "application/sparql-results+json"}, timeout=120,
                  headers={"Accept": "application/sparql-results+json"})
    r.raise_for_status()
    rows = r.json()["results"]["bindings"]
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["law_id", "title", "jurisdiction", "year", "policy_area", "instrument", "features", "celex"])
        for b in rows:
            celex = b["celex"]["value"]
            w.writerow([f"EU-{celex}", b["title"]["value"], "EU", b["date"]["value"][:4], a.policy_area or a.keyword,
                        infer_instrument(b["type"]["value"]), "", celex])
    print(f"{len(rows)} acts → {a.out}  (features column empty: tag from act text, flag as model output)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
