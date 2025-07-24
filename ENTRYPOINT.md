# Odoo Docker Image – Entrypoint script functional specification

This document reverse-engineers the current `entrypoint/entrypoint.sh` shipped
with the image and **captures every piece of business logic and technical
behaviour** that the shell script performs at run-time.  The goal is to make
it possible to re-implement, refactor or port the entrypoint in a future
session without having to consult the original Bash source.

The information is grouped by topic and follows the chronological order the
script executes at container start-up.

---

## 1. Terminology & artefacts

* **Odoo** – The ERP process executed via `/usr/bin/odoo`.
* **Redis** – Used solely as a distributed lock backend through the
  `lock-handler` CLI (not documented here, treated as a black box).
* **PostgreSQL / PgBouncer** – Primary and optional connection-pool
  endpoints.  The entrypoint can talk directly to Postgres or through
  PgBouncer depending on environment variables.
* **Semaphores** – touch-files used to persist the state of the container:
  * `DESTROY_SEMAPHORE` → `/etc/odoo/.destroy`
  * `SCAFFOLDED_SEMAPHORE` → `/etc/odoo/.scaffolded`
  * `ADDON_UPDATE_TIMESTAMP` → `/etc/odoo/.timestamp`
* **Locks** (Redis):
  * `INIT_LOCK` → `initlead` (during first-time initialisation)
  * `UPGRADE_LOCK` → `upgradelead` (during module upgrade)


---

## 2. Environment variables

The script honours a large set of variables.  Only the user-facing ones are
listed – internal helper variables are omitted.

Database / PgBouncer

| name | purpose | default |
|------|---------|---------|
| `POSTGRES_HOST` | PostgreSQL hostname | `postgres` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `POSTGRES_USER` | login | `odoo` |
| `POSTGRES_PASSWORD` | password | `odoo` |
| `POSTGRES_DB` | database name | `odoo` |
| `POSTGRES_SSL_MODE` | sslmode flag for libpq | `disable` |
| `POSTGRES_SSL_CERT/KEY/ROOT_CERT/CRL` | TLS material | *(empty)* |
| `PGBOUNCER_HOST` | if set → use PgBouncer instead of Postgres | – |
| `PGBOUNCER_PORT` | port | `5432` |
| `PGBOUNCER_SSL_MODE` | sslmode passed to Odoo | `disable` |

Add-ons & localisation

| name | purpose | default |
|------|---------|---------|
| `ODOO_LANGUAGES` | comma separated `ll_CC` list to limit l10n modules | `en_AU,en_CA,en_IN,en_NZ,en_UK,en_US` |
| `ODOO_ADDON_INIT_BLOCKLIST` | comma/space separated glob patterns to **exclude** during initialisation | – |
| `ODOO_ADDONS_TIMESTAMP` | build-time UNIX epoch; drives upgrade | – |
| `ODOO_NO_AUTO_UPGRADE` | if set, disable automatic upgrade | – |

Runtime user

| `PUID` / `PGID` | change UID/GID of user `odoo` inside the container |

Misc

| `*` | any additional flag passed to the entrypoint is forwarded to the
  final `odoo server` invocation (user-supplied options automatically override
  the defaults injected by the entrypoint). |


---

## 3. Directory layout referenced by the script

```
/opt/odoo/community   ←   copy of official community add-ons
/opt/odoo/enterprise  ←   enterprise add-ons (if present)
/opt/odoo/extras      ←   image-supplied 3rd-party modules
/mnt/addons           ←   user-mounted extra modules (optional)
/var/lib/odoo         ←   filestore & data dir
/etc/odoo/odoo.conf   ←   config file managed via `odoo-config` helper
```


---

## 4. High-level control flow

1. (Optional) **Custom command** – if the first CLI argument is **not**
   recognised as Odoo (i.e. not `odoo`, `odoo.py` or a flag starting with
   `--`) the entrypoint simply `exec`s the user command and never touches the
   rest of the logic.
2. **UID/GID mutation** via `PUID`/`PGID`.
3. **Filesystem permissions** – `chown -R odoo:odoo` on predefined target paths
   unless they are symlinks pointing back to the stock locations inside the
   image.
4. **Dependency readiness** – waits for Redis, then Postgres (or PgBouncer)
   using dedicated helper binaries `lock-handler` and `wait-for-postgres`.
5. **Initialisation phase** handled under the Redis lock `initlead`:
   1. run `odoo-addon-updater` and `odoo-config --defaults`.
   2. If `/etc/odoo/.destroy` exists → run **destroy** routine (see section
      5.1).
   3. If `/etc/odoo/.scaffolded` is **missing** → attempt restore from backup
      (`/usr/local/sbin/restore`).
      * restore succeeds → run `odoo-regenerate-assets`, mark scaffolded.
      * restore absent / failed → run destroy then **initialise** brand new
        database (see 5.2).
6. **Upgrade phase** protected by lock `upgradelead` unless
   `ODOO_NO_AUTO_UPGRADE` is set.
7. **House-keeping configuration** through `odoo-config`: master password,
   Redis section, addons path and DB connection options.
8. **Tuning**: compute number of workers = `2 * CPU – 1`; choose listen
   interface based on Odoo version (IPv6 `::` for ≥17, else `0.0.0.0`).
9. **Launch** the final `odoo server` process under `gosu odoo` with a
   comprehensive list of default flags that the user can override.


---

## 5. Detailed sub-routines

### 5.1 Destroy

Executed when the `DESTROY_SEMAPHORE` file is present _or_ when
initialisation/restore fails and a clean slate is required.

1. Terminate all active connections to `${POSTGRES_DB}` through `pg_terminate_backend()`.
2. `DROP DATABASE … WITH (FORCE)` then **recreate** it.
3. `sleep 10` to let PgBouncer flush cached connections.
4. Remove filestore directory `/var/lib/odoo/filestore/${POSTGRES_DB}`.
5. Delete both semaphore files so next start proceeds with a fresh init.

### 5.2 Initialise brand new instance

The heavy-weight part of the script.  Two passes are executed:

1. **Core-addons pass** (community + enterprise):
   * Build a curated list through `collect_addons` (dependency-sorted &
     filtered by localisation / block-list rules).
   * Ensures `web` and `base` are always present.
   * Launch `odoo --init <list> --stop-after-init --no-http`.
2. **Extras pass** (image extras + mounted `/mnt/addons`): same as above.

Upon success the `SCAFFOLDED_SEMAPHORE` file is touched and the addon
timestamp is written to `/etc/odoo/.timestamp` with a lock (uses `flock` when
available, falls back to mkdir-style lock dir).

### 5.3 Module upgrade algorithm

Triggered at every start unless `ODOO_NO_AUTO_UPGRADE` is set – but only when
`update_needed()` returns true (compares build-time
`$ODOO_ADDONS_TIMESTAMP` to the value stored in `.timestamp`).

Process:

1. Build module list with `collect_addons` (same rules as initialisation).
2. For **each** module run `odoo --update <module> --stop-after-init`.
3. Retry failed modules up to **3** attempts:
   * If **all** modules keep failing → fatal error, container stops.
   * If only a subset still fails after 3 attempts → boot continues but a
     warning is logged.
4. On every successful upgrade cycle the timestamp file is updated.


---

## 6. Helper – `collect_addons`

This reusable Bash function is responsible for turning a list of filesystem
paths into an **ordered**, **deduplicated** module list.

Algorithm summary:

1. Build set of allowed country codes from `ODOO_LANGUAGES` (extract the part
   after the underscore and lowercase it).
2. Walk every directory provided, recognise a module by the presence of
   `__manifest__.py`.
3. Apply **block-list** patterns (`ODOO_ADDON_INIT_BLOCKLIST`).
4. Apply localisation filter: `l10n_XX_*` modules are kept only when `XX`
   matches the allowed country codes.
5. Resolve dependencies using an **embedded Python topological sort** on the
   manifests; if Python is missing, fall back to discovery order.


---

## 7. Final `odoo server` invocation template

The launch helper builds an array `odoo_cmd` incrementally to allow easy
overrides.  Defaults injected **unless** already present in user args:

```
gosu odoo /usr/bin/odoo server \
  --database       $POSTGRES_DB \
  --unaccent \
  --workers        <computed> \
  --http-interface <ipv4-or-ipv6> \
  --config         /etc/odoo/odoo.conf \
  --db_host        <resolved above> \
  --db_port        … \ 
  --db_user        … \ 
  --db_password    … \ 
  --db_sslmode     … \ 
  --addons-path    <comma separated list from get_addons_paths>
  [user supplied extra flags]
```


---

## 8. Failure handling & cleanup

* `set -Eeuo pipefail` – fatal on error unless explicitly handled.
* A single `cleanup()` trap ensures held Redis locks are released on any exit
  path (SIGINT, SIGTERM, `ERR`, normal exit).


---

## 9. Known external helper binaries relied upon

* `lock-handler` – acquire / wait / release Redis locks.
* `wait-for-postgres` – block until Postgres & PgBouncer respond.
* `odoo-addon-updater` – git-based mirroring of community & enterprise repos.
* `odoo-config` – wrapper to edit / query `/etc/odoo/odoo.conf`.
* `restore` – restoration from backup volume.
* `odoo-regenerate-assets` – asset pipeline regeneration.

These need to exist or be replaced in any future re-implementation.


---

## 10. Idempotency characteristics

* **Redis locks** protect multi-replica / Kubernetes starts from parallel
  initialisation & upgrade.
* Semaphores (`.destroy`, `.scaffolded`) preserve state across restarts.
* Timestamp mechanism prevents expensive full upgrades on every boot.


---

## 11. Minimal sequence diagram

```
Container
│
├─► custom-cmd? yes → exec & exit
│
├── modify uid/gid & chown paths
├── wait Redis ─┐
├── wait DB     │
└► acquire init lock? ──► yes ── initialise/destroy/restore steps
                    │
                    └─► no  ─► wait for other pod to finish
│
├── upgrade   (under upgrade lock)
├── housekeeping (`odoo-config` …)
└── start odoo server (PID 1)
```


---

## 12. Checklist for re-implementation

1. Provide equivalents for every external helper listed in §9.
2. Preserve semaphore files and their semantics.
3. Respect all documented environment variables and default values.
4. Ensure initialisation & upgrade are **exclusive** across replicas
   (Redis-based lock).
5. Keep the two-phase module init (core vs extras) and upgrade retry logic.
6. Compute workers & listen interface as specified.
7. Allow arbitrary user flags to override defaults when launching Odoo.


---

> The above constitutes a faithful functional specification of
> `entrypoint/entrypoint.sh` as shipped in the repository at the time of
> writing.

