#!/usr/bin/env python3
"""Archive holdings → resources.csv. DOCUMENTED STUB: the archive APIs differ and some need accounts.

PARADISEC exposes an OAI-PMH endpoint (https://catalog.paradisec.org.au/oai/item?verb=ListRecords&metadataPrefix=olac);
ELAR (https://www.elararchive.org) has a public catalogue with per-deposit pages and access levels but no stable public
API as of this writing; AILLA and AIATSIS have catalogue search with CSV export. The plan:

  1. For each glottocode in languages.csv, query the catalogue by ISO 639-3 / Glottolog code (OLAC `subject.language`).
  2. From each record take: type (audio/video/text/lexicon), extent (hours, pages, entries), date, repository,
     access conditions (open / registered / closed) → open_access boolean, archive name.
  3. Write app/data/seed/resources.csv with columns: glottocode, kind, amount, year, archive, open_access.

Run with --dry-run to print the OAI request it would make for the first language. Anything the catalogues do not
state (hours not given) is left blank rather than estimated.
"""
from __future__ import annotations
import argparse, csv, sys

OAI = "https://catalog.paradisec.org.au/oai/item?verb=ListRecords&metadataPrefix=olac&set=language:{iso}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--languages", default="app/data/seed/languages.csv")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.languages)))
    if a.dry_run or True:
        first = rows[0]
        print("would request:", OAI.format(iso=first.get("iso639_3", first["glottocode"])), file=sys.stderr)
        print("STUB: implement the OLAC record parser once the archive access terms for your languages are confirmed.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
