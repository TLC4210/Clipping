"""Upload rendered clips to a public Google Cloud Storage bucket so Instagram can fetch them.

Instagram's API only accepts a public video URL (for Instagram Login), so before each Reel is
published the clip is uploaded to `gs://<gcs_bucket>/<gcs_prefix><file>` and the public
https://storage.googleapis.com/... link is handed to Instagram. After a successful publish the
object can be deleted again (`gcs_delete_after_publish`, default true) so the bucket stays empty.

Credentials, in order:
  1. `gcs_credentials` in the account config: a service-account JSON key (e.g. secrets/gcs_key.json)
  2. Application Default Credentials (`gcloud auth application-default login`)
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from .config import ROOT

SCOPE = "https://www.googleapis.com/auth/devstorage.read_write"
API = "https://storage.googleapis.com"


def enabled(acct: dict) -> bool:
    return bool(acct.get("gcs_bucket"))


def _session(acct: dict):
    from google.auth.transport.requests import AuthorizedSession

    key = acct.get("gcs_credentials")
    if key:
        from google.oauth2 import service_account

        path = ROOT / key
        if not path.exists():
            raise RuntimeError(f"No GCS service-account key at {path}")
        creds = service_account.Credentials.from_service_account_file(str(path), scopes=[SCOPE])
    else:
        import google.auth

        creds, _ = google.auth.default(scopes=[SCOPE])
    return AuthorizedSession(creds)


def object_name(acct: dict, path: Path, niche: str | None = None) -> str:
    prefix = acct.get("gcs_prefix")
    if prefix is None:
        prefix = f"{niche}/" if niche else ""
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return f"{prefix}{path.name}"


def public_url(bucket: str, name: str) -> str:
    return f"{API}/{bucket}/{quote(name)}"


def upload(acct: dict, path: Path, niche: str | None = None, session=None) -> dict:
    """Upload `path`; returns {"bucket", "name", "url"}."""
    bucket = acct["gcs_bucket"]
    name = object_name(acct, path, niche)
    s = session or _session(acct)
    with open(path, "rb") as fh:
        r = s.post(f"{API}/upload/storage/v1/b/{quote(bucket, safe='')}/o",
                   params={"uploadType": "media", "name": name},
                   headers={"Content-Type": "video/mp4"}, data=fh, timeout=600)
    if r.status_code >= 400:
        raise RuntimeError(f"GCS upload failed {r.status_code}: {r.text[:300]}")
    return {"bucket": bucket, "name": name, "url": public_url(bucket, name)}


def delete(acct: dict, name: str, session=None) -> None:
    s = session or _session(acct)
    r = s.delete(f"{API}/storage/v1/b/{quote(acct['gcs_bucket'], safe='')}/o/{quote(name, safe='')}",
                 timeout=60)
    if r.status_code not in (200, 204, 404):
        raise RuntimeError(f"GCS delete failed {r.status_code}: {r.text[:300]}")
