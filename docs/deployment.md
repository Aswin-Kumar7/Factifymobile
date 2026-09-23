# Deployment and runtime sizing (M49)

Run the thing, at the right size, in the right place. Every number here is a
decision with a stated consequence rather than a platform default left in place.

---

## Shape

One container serves the API. Not seven microservices — the modules are internal,
and splitting them would buy independent scaling nobody needs at this volume while
costing a network hop on every evidence lookup.

**Ingestion is a separate short-lived job that exits after each batch.** Never inside
the web process: Cloud Run instances scale to zero and multiply, so an in-process
timer either stops firing or fires N times, and both are silent. The trigger comes
from outside (Cloud Scheduler), authenticated with a shared secret compared in
constant time.

---

## Memory

**Request at least 2 GiB.** The default 512 MiB will not survive what this process
actually loads:

| Resident cost | Approximate |
|---|---|
| Python, FastAPI, psycopg pool | ~120 MiB |
| Text embedding model (ONNX, 384-d) | ~250 MiB |
| Image embedding model (CLIP ViT-B/32, 512-d) | ~350 MiB |
| Pillow decoding a 25 MB upload | ~200 MiB transient |
| ffmpeg decoding 90 s at 480p | ~150 MiB transient |

Both models stay resident for the life of the instance — that is the point of local
inference — so the floor is roughly 720 MiB before a single request, and the
transient peaks land on top of it. 2 GiB leaves headroom for two concurrent
image requests; 1 GiB does not.

**CPU: 2 vCPU.** ONNX inference is CPU-bound and single-request latency matters more
than throughput here.

---

## Cold start

**Keep one warm instance during judging.** Scale-to-zero plus local models is a
direct collision with the 3–8 second latency target:

- Container start: ~2 s
- Model load from the baked-in cache: ~4 s
- First request then pays extraction on top

Without a warm instance the first request — the one most likely to be a judge's —
takes ten seconds or more. The models are baked into the image at build time rather
than downloaded on first use, which removes ~36 s of download from that path but not
the load itself.

A warm instance is billed continuously. That is the cost of the latency target, and
it is a deliberate trade rather than an oversight.

---

## Region

**`asia-south1` (Mumbai).**

The corpus is Indian, the sources are Indian, and the users are Indian. Every
ingestion fetch and every evidence retrieval crosses the shortest path from there.
Serving from `us-central1` would add roughly 200 ms round-trip to every source fetch,
and a verification makes several — which is a meaningful fraction of an 8 second
budget spent on geography.

Cost consequence: `asia-south1` is not among the cheapest regions, and it is not
covered by the always-free Cloud Run tier the way `us-central1` is. Recorded as a
deliberate choice: latency to sources beats free-tier eligibility for a product whose
core operation is fetching Indian pages.

The database is also `ap-south-1`, so the service and its data sit together.

---

## Secrets

Every credential goes in Secret Manager and is referenced with `--set-secrets`, never
`--set-env-vars`. Environment variables set that way are readable by anyone with view
access on the service and persist in deployment history; a secret reference resolves
at instance start.

Required at runtime:

| Secret | Consequence if absent |
|---|---|
| `FACTIFY_DATABASE_URL` | Service refuses to boot outside `local` |
| `FACTIFY_LLM__API_KEY` | Claim extraction abstains, and says so |
| `FACTIFY_INGEST_TRIGGER_SECRET` | Every ingestion trigger is denied |
| `FACTIFY_RECEIPT_SIGNING_KEY` | Receipts are not issued |

**No credential is ever shipped to a client.** The Android app holds none; it talks
only to this service. A key in an APK is a key extracted from that APK.

---

## Frozen before demo day

Pin and do not move:

- `uv.lock` — the dependency set, already committed
- `FACTIFY_MODELS__EXTRACTION` — pinned to a specific model id, not a moving alias
  like `gemini-flash-latest`. A silently repointed alias changes extraction
  behaviour; the model id is part of the verdict cache key so a change invalidates
  cached results rather than serving stale ones, but a pin makes it a deliberate
  edit rather than a surprise.
- The base image digest, once the final build is cut.

---

## What is verified, and what is not

| Item | Status |
|---|---|
| Image builds | ⏳ Docker unavailable on the development machine; the CI `image` job builds and probes `/healthz` |
| Cold deployment serves within the latency target | ⏳ Blocked on a first deploy |
| Ingestion runs as a job on its own schedule | ⏳ Blocked on the Cloud Scheduler decision |
| Memory figures above | ⚠️ Estimated from model sizes and decode buffers, **not measured under load** |

The memory table is the honest weak point: it is arithmetic, not a profile. Measure
it against a running instance before trusting the 2 GiB figure, and record the real
numbers here in its place.
