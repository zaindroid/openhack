# Seed data — ILLUSTRATIVE

Every row here is invented. Names are placeholders ("Language A (Andes)"), glottocodes are `illu####`, and all
speaker counts, ages, hours and access facts were constructed to exercise the agent's tests. No real endangered
language is described with invented numbers on purpose: wrong figures about real communities would be harmful.

## Column mapping to real sources
| table.column | real source | notes |
|---|---|---|
| languages.glottocode, name, family, lat, lon | Glottolog languoid CSV (`glottolog-cldf` `languages.csv`) | `fetch_glottolog.py` |
| languages.endangerment | Glottolog AES status (`values.csv`, parameter `aes`) → vulnerable/definitely/severely/critically | `fetch_glottolog.py` maps AES codes |
| languages.speakers, speakers_year | UNESCO World Atlas of Languages; Ethnologue (paid); community censuses | manual |
| languages.median_speaker_age, intergenerational_transmission | UNESCO WAL vitality factors; fieldwork reports | manual |
| resources.* | ELAR / PARADISEC / AILLA / AIATSIS catalogue records (OAI-PMH or CSV export): extent → hours/entries/pages, access conditions → open_access, repository → archive | `fetch_elar.py` (stub) |
| access.* | fieldwork reports, national research-permit rules, community organisations | manual |
| projects.* | ELDP / DOBES / NSF-DEL grant lists, archive deposit metadata | manual |

Replace a CSV with a real extract and keep the column names; `python -m whycore.evals app/evals.yaml` will then
fail on the illustrative cases — rewrite `app/evals.yaml` against documented real cases.
