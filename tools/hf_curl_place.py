"""Populate a Hugging Face cache entry with curl, because Python cannot reach the Hub here.

**When you need this.** Any time a model id changes and its weights are not already cached. The
application's own downloader cannot run on this machine at all -- `bootstrap.download_models` and
the settings page's availability check both go through `huggingface_hub`, which fails here for the
reason below. Everything the product currently needs is cached, so nothing is broken today; the
first change to a model id is when it bites, and the error it raises reads as "no internet" rather
than as what it is.

    .venv/bin/python tools/hf_curl_place.py <hub-dir> <repo-id> <file> [<file> ...]

    HUB="$PWD/.hf_cache/AegisPrompter/models/hub"
    .venv/bin/python tools/hf_curl_place.py "$HUB" some-org/some-model config.json model.safetensors

Gated repositories still answer 401 and this cannot help with those -- that needs a token, which is
the thing **V93** went to some trouble to avoid needing.

`huggingface_hub` verifies TLS against `certifi` and this machine's traffic is intercepted by a
Cloudflare Gateway CA that lives in the System keychain, so every Python fetch dies on
CERTIFICATE_VERIFY_FAILED while curl -- which uses the system trust store -- gets a 200. The
operator chose curl-and-place over making Python trust the interception CA (2026-08-19), so this
changes nothing about what any tool trusts.

Layout replicated from the working `ivrit-ai/pyannote-segmentation-3.0` entry rather than from
documentation: blobs/<sha256-of-content>, snapshots/<commit>/<file> symlinked to the blob, and
refs/main holding the commit. Verified afterwards by an offline `hf_hub_download`.
"""
import hashlib, json, os, subprocess, sys

HUB = os.path.abspath(sys.argv[1])
REPO = sys.argv[2]
FILES = sys.argv[3:]

def curl(url, dest=None):
    cmd = ["curl", "-sSL", "--max-time", "900", url]
    if dest:
        cmd += ["-o", dest]
    r = subprocess.run(cmd, capture_output=not dest, text=not dest)
    if r.returncode != 0:
        raise SystemExit(f"curl failed for {url}: {getattr(r, 'stderr', '')}")
    return None if dest else r.stdout

info = json.loads(curl(f"https://huggingface.co/api/models/{REPO}"))
sha = info["sha"]
root = os.path.join(HUB, "models--" + REPO.replace("/", "--"))
snap = os.path.join(root, "snapshots", sha)
blobs = os.path.join(root, "blobs")
os.makedirs(snap, exist_ok=True)
os.makedirs(blobs, exist_ok=True)
os.makedirs(os.path.join(root, "refs"), exist_ok=True)

for name in FILES:
    tmp = os.path.join(blobs, ".incoming")
    curl(f"https://huggingface.co/{REPO}/resolve/{sha}/{name}", tmp)
    digest = hashlib.sha256(open(tmp, "rb").read()).hexdigest()
    blob = os.path.join(blobs, digest)
    os.replace(tmp, blob)
    link = os.path.join(snap, name)
    os.makedirs(os.path.dirname(link), exist_ok=True)
    if os.path.lexists(link):
        os.remove(link)
    os.symlink(os.path.relpath(blob, os.path.dirname(link)), link)
    print(f"  {name:<24} {os.path.getsize(blob):>12,} bytes")

with open(os.path.join(root, "refs", "main"), "w") as fh:
    fh.write(sha)
print(f"  refs/main -> {sha}")
