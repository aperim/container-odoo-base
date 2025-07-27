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

### 7.1 Current odoo flags/parameters

```zsh
root@server:/# odoo --help
Running as user 'root' is a security risk.
Usage: odoo server [options]

Options:
  --version             show program's version number and exit
  -h, --help            show this help message and exit

  Common options:
    -c CONFIG, --config=CONFIG
                        specify alternate config file
    -s, --save          save configuration to ~/.odoorc (or to
                        ~/.openerp_serverrc if it exists)
    -i INIT, --init=INIT
                        install one or more modules (comma-separated list, use
                        "all" for all modules), requires -d
    -u UPDATE, --update=UPDATE
                        update one or more modules (comma-separated list, use
                        "all" for all modules). Requires -d.
    --without-demo=WITHOUT_DEMO
                        disable loading demo data for modules to be installed
                        (comma-separated, use "all" for all modules). Requires
                        -d and -i. Default is none
    -P IMPORT_PARTIAL, --import-partial=IMPORT_PARTIAL
                        Use this for big data importation, if it crashes you
                        will be able to continue at the current state. Provide
                        a filename to store intermediate importation states.
    --pidfile=PIDFILE   file where the server pid will be stored
    --addons-path=ADDONS_PATH
                        specify additional addons paths (separated by commas).
    --upgrade-path=UPGRADE_PATH
                        specify an additional upgrade path.
    --pre-upgrade-scripts=PRE_UPGRADE_SCRIPTS
                        Run specific upgrade scripts before loading any module
                        when -u is provided.
    --load=SERVER_WIDE_MODULES
                        Comma-separated list of server-wide modules.
    -D DATA_DIR, --data-dir=DATA_DIR
                        Directory where to store Odoo data

  HTTP Service Configuration:
    --http-interface=HTTP_INTERFACE
                        Listen interface address for HTTP services. Keep empty
                        to listen on all interfaces (0.0.0.0)
    -p PORT, --http-port=PORT
                        Listen port for the main HTTP service
    --gevent-port=PORT  Listen port for the gevent worker
    --no-http           Disable the HTTP and Longpolling services entirely
    --proxy-mode        Activate reverse proxy WSGI wrappers (headers
                        rewriting) Only enable this when running behind a
                        trusted web proxy!
    --x-sendfile        Activate X-Sendfile (apache) and X-Accel-Redirect
                        (nginx) HTTP response header to delegate the delivery
                        of large files (assets/attachments) to the web server.

  Web interface Configuration:
    --db-filter=REGEXP  Regular expressions for filtering available databases
                        for Web UI. The expression can use %d (domain) and %h
                        (host) placeholders.

  Testing Configuration:
    --test-file=TEST_FILE
                        Launch a python test file.
    --test-enable       Enable unit tests.
    --test-tags=TEST_TAGS
                        Comma-separated list of specs to filter which tests to
                        execute. Enable unit tests if set. A filter spec has
                        the format:
                        [-][tag][/module][:class][.method][[params]] The '-'
                        specifies if we want to include or exclude tests
                        matching this spec. The tag will match tags added on a
                        class with a @tagged decorator (all Test classes have
                        'standard' and 'at_install' tags until explicitly
                        removed, see the decorator documentation). '*' will
                        match all tags. If tag is omitted on include mode, its
                        value is 'standard'. If tag is omitted on exclude
                        mode, its value is '*'. The module, class, and method
                        will respectively match the module name, test class
                        name and test method name. Example: --test-tags
                        :TestClass.test_func,/test_module,external It is also
                        possible to provide parameters to a test method that
                        supports themExample: --test-tags /web.test_js[mail]If
                        negated, a test-tag with parameter will negate the
                        parameter when passing it to the testFiltering and
                        executing the tests happens twice: right after each
                        module installation/update and at the end of the
                        modules loading. At each stage tests are filtered by
                        --test-tags specs and additionally by dynamic specs
                        'at_install' and 'post_install' correspondingly.
    --screencasts=DIR   Screencasts will go in DIR/{db_name}/screencasts.
    --screenshots=DIR   Screenshots will go in DIR/{db_name}/screenshots.
                        Defaults to /tmp/odoo_tests.

  Logging Configuration:
    --logfile=LOGFILE   file where the server log will be stored
    --syslog            Send the log to the syslog server
    --log-handler=PREFIX:LEVEL
                        setup a handler at LEVEL for a given PREFIX. An empty
                        PREFIX indicates the root logger. This option can be
                        repeated. Example: "odoo.orm:DEBUG" or
                        "werkzeug:CRITICAL" (default: ":INFO")
    --log-web           shortcut for --log-handler=odoo.http:DEBUG
    --log-sql           shortcut for --log-handler=odoo.sql_db:DEBUG
    --log-db=LOG_DB     Logging database
    --log-db-level=LOG_DB_LEVEL
                        Logging database level
    --log-level=LOG_LEVEL
                        specify the level of the logging. Accepted values:
                        ['info', 'debug_rpc', 'warn', 'test', 'critical',
                        'runbot', 'debug_sql', 'error', 'debug',
                        'debug_rpc_answer', 'notset'].

  SMTP Configuration:
    --email-from=EMAIL_FROM
                        specify the SMTP email address for sending email
    --from-filter=FROM_FILTER
                        specify for which email address the SMTP configuration
                        can be used
    --smtp=SMTP_SERVER  specify the SMTP server for sending email
    --smtp-port=SMTP_PORT
                        specify the SMTP port
    --smtp-ssl          if passed, SMTP connections will be encrypted with SSL
                        (STARTTLS)
    --smtp-user=SMTP_USER
                        specify the SMTP username for sending email
    --smtp-password=SMTP_PASSWORD
                        specify the SMTP password for sending email
    --smtp-ssl-certificate-filename=SMTP_SSL_CERTIFICATE_FILENAME
                        specify the SSL certificate used for authentication
    --smtp-ssl-private-key-filename=SMTP_SSL_PRIVATE_KEY_FILENAME
                        specify the SSL private key used for authentication

  Database related options:
    -d DB_NAME, --database=DB_NAME
                        specify the database name
    -r DB_USER, --db_user=DB_USER
                        specify the database user name
    -w DB_PASSWORD, --db_password=DB_PASSWORD
                        specify the database password
    --pg_path=PG_PATH   specify the pg executable path
    --db_host=DB_HOST   specify the database host
    --db_replica_host=DB_REPLICA_HOST
                        specify the replica host. Specify an empty
                        db_replica_host to use the default unix socket.
    --db_port=DB_PORT   specify the database port
    --db_replica_port=DB_REPLICA_PORT
                        specify the replica port
    --db_sslmode=DB_SSLMODE
                        specify the database ssl connection mode (see
                        PostgreSQL documentation)
    --db_maxconn=DB_MAXCONN
                        specify the maximum number of physical connections to
                        PostgreSQL
    --db_maxconn_gevent=DB_MAXCONN_GEVENT
                        specify the maximum number of physical connections to
                        PostgreSQL specifically for the gevent worker
    --db-template=DB_TEMPLATE
                        specify a custom database template to create a new
                        database

  Internationalisation options:
    Use these options to translate Odoo to another language. See i18n
    section of the user manual. Option '-d' is mandatory. Option '-l' is
    mandatory in case of importation

    --load-language=LOAD_LANGUAGE
                        specifies the languages for the translations you want
                        to be loaded
    -l LANGUAGE, --language=LANGUAGE
                        specify the language of the translation file. Use it
                        with --i18n-export or --i18n-import
    --i18n-export=TRANSLATE_OUT
                        export all sentences to be translated to a CSV file, a
                        PO file or a TGZ archive and exit
    --i18n-import=TRANSLATE_IN
                        import a CSV or a PO file with translations and exit.
                        The '-l' option is required.
    --i18n-overwrite    overwrites existing translation terms on updating a
                        module or importing a CSV or a PO file.
    --modules=TRANSLATE_MODULES
                        specify modules to export. Use in combination with
                        --i18n-export

  Security-related options:
    --no-database-list  Disable the ability to obtain or view the list of
                        databases. Also disable access to the database manager
                        and selector, so be sure to set a proper --database
                        parameter first

  Advanced options:
    --dev=DEV_MODE      Enable developer mode. Param: List of options
                        separated by comma. Options : all, reload, qweb, xml
    --shell-interface=SHELL_INTERFACE
                        Specify a preferred REPL to use in shell mode.
                        Supported REPLs are: [ipython|ptpython|bpython|python]
    --stop-after-init   stop the server after its initialization
    --osv-memory-count-limit=OSV_MEMORY_COUNT_LIMIT
                        Force a limit on the maximum number of records kept in
                        the virtual osv_memory tables. By default there is no
                        limit.
    --transient-age-limit=TRANSIENT_AGE_LIMIT
                        Time limit (decimal value in hours) records created
                        with a TransientModel (mostly wizard) are kept in the
                        database. Default to 1 hour.
    --max-cron-threads=MAX_CRON_THREADS
                        Maximum number of threads processing concurrently cron
                        jobs (default 2).
    --limit-time-worker-cron=LIMIT_TIME_WORKER_CRON
                        Maximum time a cron thread/worker stays alive before
                        it is restarted. Set to 0 to disable. (default: 0)
    --unaccent          Try to enable the unaccent extension when creating new
                        databases.
    --geoip-city-db=GEOIP_CITY_DB, --geoip-db=GEOIP_CITY_DB
                        Absolute path to the GeoIP City database file.
    --geoip-country-db=GEOIP_COUNTRY_DB
                        Absolute path to the GeoIP Country database file.

  Multiprocessing options:
    --workers=WORKERS   Specify the number of workers, 0 disable prefork mode.
    --limit-memory-soft=LIMIT_MEMORY_SOFT
                        Maximum allowed virtual memory per worker (in bytes),
                        when reached the worker be reset after the current
                        request (default 2048MiB).
    --limit-memory-soft-gevent=LIMIT_MEMORY_SOFT_GEVENT
                        Maximum allowed virtual memory per gevent worker (in
                        bytes), when reached the worker will be reset after
                        the current request. Defaults to `--limit-memory-
                        soft`.
    --limit-memory-hard=LIMIT_MEMORY_HARD
                        Maximum allowed virtual memory per worker (in bytes),
                        when reached, any memory allocation will fail (default
                        2560MiB).
    --limit-memory-hard-gevent=LIMIT_MEMORY_HARD_GEVENT
                        Maximum allowed virtual memory per gevent worker (in
                        bytes), when reached, any memory allocation will fail.
                        Defaults to `--limit-memory-hard`.
    --limit-time-cpu=LIMIT_TIME_CPU
                        Maximum allowed CPU time per request (default 60).
    --limit-time-real=LIMIT_TIME_REAL
                        Maximum allowed Real time per request (default 120).
    --limit-time-real-cron=LIMIT_TIME_REAL_CRON
                        Maximum allowed Real time per cron job. (default:
                        --limit-time-real). Set to 0 for no limit.
    --limit-request=LIMIT_REQUEST
                        Maximum number of request to be processed per worker
                        (default 65536).
root@server:/# odoo --version
Running as user 'root' is a security risk.
Odoo Server 18.0-20250618
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

