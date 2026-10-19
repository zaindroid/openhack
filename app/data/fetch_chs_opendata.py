"""Documented STUB: permits and pending decisions for the Mar Menor basin.

Sources (all public, formats not yet confirmed from a machine with internet):
  - CHS (Confederación Hidrográfica del Segura) — concessions (abstraction) and discharge authorisations:
      https://www.chsegura.es  → "Transparencia" / "Registro de Aguas"; expect PDF or CSV tables per concession:
      holder, kind, volume (m³/yr), coordinates or municipality, status, expiry.
  - CARM (Región de Murcia) — fertiliser application plans under Ley 3/2020 and public-consultation notices:
      https://www.carm.es → "Participación ciudadana" and the BORM (https://www.borm.es) for notices with deadlines.
  - Municipal planning registers (Cartagena, Los Alcázares, San Javier, San Pedro del Pinatar): public notice boards.
Output columns (match app/data/seed/):
  permits.csv  : permit_id, holder, kind{abstraction|discharge|fertiliser_plan}, volume, unit, distance_km, status, expiry
  decisions.csv: decision_id, title, authority, kind{planning|permit_renewal|infrastructure}, distance_km, submitted, deadline, status, summary
distance_km = great-circle distance from the record's coordinates (or municipality centroid) to the client's lat/lon in clients.csv.
Until the API shape is confirmed, fill these CSVs by hand from the notices and keep the source URL in the summary field.
"""
import sys

if __name__ == "__main__":
    print(__doc__)
    sys.exit(0)
