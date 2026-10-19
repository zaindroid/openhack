"""Where ex-post evaluation reports live, and how they become `evaluations` rows. Documented stub: the report
sources are PDF libraries without a uniform API, so this script lists them, downloads a given set of PDFs, and
produces an EMPTY evaluations.csv with the law_id/url filled in for the extraction step.

Report sources (all free):
  European Commission ex-post evaluations and fitness checks
      https://commission.europa.eu/law/law-making-process/evaluating-and-improving-existing-laws_en
      (the "Have your say" portal lists evaluations per initiative; SWD(...) staff working documents are the reports)
  European Court of Auditors special reports           https://www.eca.europa.eu/en/publications
  Bundesrechnungshof (DE) Bemerkungen / Prüfberichte     https://www.bundesrechnungshof.de/de/veroeffentlichungen
  National Audit Office (UK) reports                     https://www.nao.org.uk/reports/
  Cour des comptes (FR) rapports                          https://www.ccomptes.fr/fr/publications
  Tribunal de Cuentas (ES) informes                       https://www.tcu.es/tribunal-de-cuentas/es/fiscalizacion/
  Algemene Rekenkamer (NL) rapporten                      https://www.rekenkamer.nl/publicaties
  OECD policy evaluations                                 https://www.oecd.org/en/topics/policy-evaluation.html

Extraction plan (day 2 of the build, inside the agent, through Meterless → Nemotron):
  1. For each report PDF: text → chunks tagged with law_id.
  2. Prompt: classify each finding into finding_type ∈ {gaming, cost_overrun, enforcement_gap, equity_harm,
     take_up_shortfall, unintended_market_effect, none} with magnitude ∈ {low, medium, high} and a one-sentence
     summary that quotes the report. Output JSON only.
  3. Store rows with body = report author, url = the PDF, and the column `extracted_by = model` so the UI can label
     them as model output (the seed rows are hand-entered and carry no such label). A human reviews before the demo.

Usage:
    python app/data/fetch_evaluations.py --pdf-list app/data/raw/reports.csv --out app/data/raw/evaluations_skeleton.csv
where reports.csv has columns law_id,url,body,year.
"""
from __future__ import annotations
import argparse, csv, os, sys
import httpx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-list", required=True)
    ap.add_argument("--out", default="app/data/raw/evaluations_skeleton.csv")
    ap.add_argument("--download-dir", default="app/data/raw/reports")
    a = ap.parse_args()
    os.makedirs(a.download_dir, exist_ok=True)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    n = 0
    with open(a.pdf_list) as f, open(a.out, "w", newline="") as out:
        w = csv.writer(out)
        w.writerow(["eval_id", "law_id", "year", "body", "finding_type", "magnitude", "summary", "url", "extracted_by", "local_pdf"])
        for i, row in enumerate(csv.DictReader(f), 1):
            local = os.path.join(a.download_dir, f"{row['law_id']}_{i}.pdf")
            try:
                with httpx.stream("GET", row["url"], timeout=120, follow_redirects=True) as r:
                    r.raise_for_status()
                    with open(local, "wb") as pdf:
                        for chunk in r.iter_bytes():
                            pdf.write(chunk)
            except Exception as e:  # keep the row; the extraction step can retry
                local = f"download failed: {str(e)[:80]}"
            w.writerow([f"X{i:03d}", row["law_id"], row.get("year", ""), row.get("body", ""), "", "", "", row["url"], "pending", local])
            n += 1
    print(f"{n} reports listed → {a.out}; run the extraction step to fill finding_type/magnitude/summary")
    return 0


if __name__ == "__main__":
    sys.exit(main())
