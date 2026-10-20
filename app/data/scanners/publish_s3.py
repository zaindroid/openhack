"""Publish a scan to S3 so Zetaris reads the evidence from object storage, not from local files.

Writes the inventory produced by the scanners as typed Parquet to the bucket MOSCA_S3_BUCKET (default `mosca`):
  inventory/scans/assets/scan_date=<YYYY-MM-DD>/assets.parquet   history, one partition per scan day (mosca_s3.assets_history)
  inventory/scans/probes/scan_date=<YYYY-MM-DD>/probes.parquet
  inventory/current/assets/assets.parquet                  what the app reads (Zetaris table mosca_s3.assets)
  inventory/current/probes/probes.parquet
Each object carries the sha256 of the CSV it was made from (metadata source-sha256), so every row the agent cites traces
back to one scan file. Editable reference tables (data_classes, migration_paths, scenarios) stay in Postgres (mosca_pg).

  python app/data/scanners/publish_s3.py      # MOSCA_S3_ENDPOINT (default http://127.0.0.1:9000), MOSCA_S3_ACCESS_KEY,
                                              # MOSCA_S3_SECRET_KEY from the environment or infra/.env"""
from __future__ import annotations
import csv, hashlib, io, os, sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
INV = os.environ.get("INVENTORY_DIR", os.path.join(HERE, "..", "inventory"))


def env() -> None:
    p = os.path.join(ROOT, "infra", ".env")
    if os.path.exists(p):
        for line in open(p).read().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1); os.environ.setdefault(k.strip(), v.strip())


def table(path: str, kind: str):
    import pyarrow as pa
    rows = list(csv.DictReader(open(path, newline="")))
    if kind == "assets":
        b = lambda v: str(v).strip().lower() == "true"
        f = lambda v: float(v) if str(v).strip() not in ("", "None") else 0.0
        d = lambda v: date.fromisoformat(v) if v else None
        schema = pa.schema([(c, pa.string()) for c in ("asset_id", "name", "host", "port", "kind", "algorithm", "key_bits", "purpose",
                                                        "negotiated_kex", "negotiated_sig")] +
                           [("expires", pa.date32()), ("in_use", pa.bool_()), ("data_class", pa.string()), ("traffic_gb_month", pa.float64()),
                            ("source", pa.string()), ("found_at", pa.date32()), ("note", pa.string())])
        conv = {"expires": d, "in_use": b, "traffic_gb_month": f, "found_at": d}
    else:
        schema = pa.schema([("source", pa.string()), ("target", pa.string()), ("outcome", pa.string()), ("probed_at", pa.date32())])
        conv = {"probed_at": lambda v: date.fromisoformat(v) if v else None}
    cols = {n: [conv.get(n, lambda v: v if v != "" else None)(r.get(n, "")) for r in rows] for n in schema.names}
    return pa.table(cols, schema=schema), len(rows)


def main() -> int:
    import boto3
    import pyarrow.parquet as pq
    env()
    s3 = boto3.client("s3", endpoint_url=os.environ.get("MOSCA_S3_ENDPOINT", "http://127.0.0.1:9000"),
                      aws_access_key_id=os.environ["MOSCA_S3_ACCESS_KEY"], aws_secret_access_key=os.environ["MOSCA_S3_SECRET_KEY"],
                      region_name="us-east-1")
    bucket = os.environ.get("MOSCA_S3_BUCKET", "mosca")
    for kind in ("assets", "probes"):
        src = os.path.join(INV, f"{kind}.csv")
        raw = open(src, "rb").read()
        sha = hashlib.sha256(raw).hexdigest()
        t, n = table(src, kind)
        scan_day = max((r for r in t.column("found_at" if kind == "assets" else "probed_at").to_pylist() if r), default=date.today())
        buf = io.BytesIO(); pq.write_table(t, buf, compression="zstd"); body = buf.getvalue()
        meta = {"source-sha256": sha, "source-file": f"app/data/inventory/{kind}.csv", "rows": str(n)}
        for key in (f"inventory/scans/{kind}/scan_date={scan_day.isoformat()}/{kind}.parquet", f"inventory/current/{kind}/{kind}.parquet"):
            s3.put_object(Bucket=bucket, Key=key, Body=body, Metadata=meta, ContentType="application/vnd.apache.parquet")
            print(f"s3://{bucket}/{key}  rows={n}  csv sha256={sha[:16]}…")
    return 0


if __name__ == "__main__":
    sys.exit(main())
