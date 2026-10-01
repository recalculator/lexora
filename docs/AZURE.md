# Azure benchmark environment

How to reproduce the Azure Database for PostgreSQL setup used for `make bench ENV=azure`. The
protocol (what's measured and how it differs from the local run) is the "Azure protocol" amendment
in `bench/PREREGISTRATION.md`. This file covers only setup.

**Never put the connection string, password or server hostname in any file in this repo**,
including results, docs, compose files and commit messages. Containers get `DATABASE_URL` by
name only (`docker run -e DATABASE_URL`). Results record the host as `<azure-flexible-server>`.

## Target configuration

| Setting | Value |
|---|---|
| Service | Azure Database for PostgreSQL Flexible Server |
| Compute | Burstable, Standard_B1ms (1 vCore, 2 GiB RAM) |
| Storage | 32 GiB, performance tier P4 (120 IOPS) |
| PostgreSQL | 16 (16.15 at setup time) |
| pgvector | 0.8.2 at setup time (local Docker has 0.8.6) |
| Region | Canada Central (`canadacentral`) |
| Networking | Public access, client IP allowlisted, SSL required |
| High availability | Disabled |
| Database | `postgres` (default) |

### Azure for Students: region policy

Azure for Students subscriptions restrict the regions you can deploy to through an Azure Policy
assignment. On the subscription used here the allowed regions were `westus`, `norwayeast`,
`francecentral`, `denmarkeast` and `canadacentral`, which is why this server is in Canada Central.
The allowed list belongs to that subscription and can differ for yours. If a create fails with a
policy error, choose a region from the list the error (or the subscription's Policy assignments
in the portal) reports. The client for the recorded run is in Champaign, Illinois, so Canada
Central adds a cross-border network path. That's why server-side execution time, not client
round trip, is the cross-environment comparison.

## 1. Create the server

### Portal

1. **Create a resource > Azure Database for PostgreSQL Flexible Server > Create.**
2. **Basics:** pick the subscription and a resource group, a server name, region **Canada Central**,
   PostgreSQL version **16**, workload type **Development**. Under **Compute + storage > Configure
   server**, choose **Burstable**, **Standard_B1ms**, storage **32 GiB**, performance tier **P4**,
   and disable storage autogrow and high availability. Set an admin username and password.
3. **Networking:** connectivity method **Public access (allowed IP addresses)**, then **Add current
   client IP address**.
4. **Review + create > Create.**

### Azure CLI

```bash
RG=lexora-bench
SERVER=<server-name>           # globally unique
LOCATION=canadacentral
ADMIN_USER=<admin-user>
MY_IP=<your public IPv4>
read -rs PGPASSWORD_NEW        # type the admin password; it doesn't echo or go into shell history

az group create --name "$RG" --location "$LOCATION"

az postgres flexible-server create \
  --resource-group "$RG" --name "$SERVER" --location "$LOCATION" \
  --tier Burstable --sku-name Standard_B1ms \
  --storage-size 32 --version 16 \
  --zonal-resiliency Disabled --storage-auto-grow Disabled \
  --admin-user "$ADMIN_USER" --admin-password "$PGPASSWORD_NEW" \
  --public-access "$MY_IP"
```

`--public-access <ip>` allowlists that address at creation. To add or change the address later:

```bash
az postgres flexible-server firewall-rule create \
  --resource-group "$RG" --server-name "$SERVER" \
  --name client-home --start-ip-address "$MY_IP" --end-ip-address "$MY_IP"
```

## 2. Allowlist pgvector

Azure only allows `CREATE EXTENSION` for extensions listed in the `azure.extensions` server
parameter.

- **Portal:** server > **Settings > Server parameters**, find `azure.extensions`, tick **VECTOR**,
  **Save**, and wait for the deployment to finish.
- **CLI:**

  ```bash
  az postgres flexible-server parameter set \
    --resource-group "$RG" --server-name "$SERVER" \
    --name azure.extensions --value VECTOR
  az postgres flexible-server parameter show \
    --resource-group "$RG" --server-name "$SERVER" --name azure.extensions
  ```

Migration `003_add_pgvector` runs `CREATE EXTENSION IF NOT EXISTS vector`. That succeeds once
the extension is allowlisted, and also if it was already created by hand.

## 3. Point the tools at the server

Export `DATABASE_URL` in the shell you'll run `make` from. Don't write it to a file.

```bash
export DATABASE_URL='postgresql://<admin-user>:<url-encoded-password>@<server-name>.postgres.database.azure.com:5432/postgres?sslmode=require'
```

URL-encode special characters in the password (for example `@` as `%40`). `alembic/env.py`
escapes `%` for Alembic's config parser, so percent-encoded passwords work. To check that it's
set without printing it: `[ -n "$DATABASE_URL" ] && echo set`.

## 4. Migrate

```bash
make bench-image
docker run --rm -e DATABASE_URL -v "$PWD:/repo" -w /repo/backend lexora-bench alembic upgrade head
```

Check: `SELECT version_num FROM alembic_version` returns `004_reference_categories_array`, and the
`reference_clauses` indexes are the GIN index on `categories`, the HNSW index
`ix_reference_clauses_embedding_hnsw` (m=16, ef_construction=64) and the primary key.

## 5. Load the corpus, then rebuild the HNSW index

```bash
make load-corpus ENV=azure      # writes bench/results/load_<timestamp>_azure.json
```

The loader checks 6,766 rows, 0 null embeddings and per-category counts against the corpus
before it writes the load record. On Azure, the HNSW index is then rebuilt from scratch on the
loaded table and the table is vacuumed and analyzed. This is a deliberate protocol difference
from the local run, where the index existed during the load:

```bash
docker run --rm -i -e DATABASE_URL pgvector/pgvector:pg16 \
  sh -c 'psql "$DATABASE_URL" -v ON_ERROR_STOP=1' <<'SQL'
\timing on
DROP INDEX ix_reference_clauses_embedding_hnsw;
CREATE INDEX ix_reference_clauses_embedding_hnsw ON reference_clauses
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
VACUUM ANALYZE reference_clauses;
SELECT count(*) AS rows, count(*) FILTER (WHERE embedding IS NULL) AS null_embeddings FROM reference_clauses;
SELECT pg_relation_size('ix_reference_clauses_embedding_hnsw'::regclass) AS hnsw_bytes;
SQL
```

`make bench` records the index definition, size and the table's vacuum/analyze timestamps at the
start of the run (`index_state_at_start`), so the results file shows the state the run used.

## 6. Run the benchmark

The working tree must be clean so the results record a real commit. Set the metadata the
harness records. It refuses to start an Azure run without them:

```bash
export BENCH_AZURE_REGION=canadacentral
export BENCH_AZURE_SKU='Burstable Standard_B1ms (1 vCore, 2 GiB RAM), 32 GiB storage P4 (120 IOPS)'
export BENCH_CLIENT_LOCATION='Champaign, Illinois (home network)'
make bench ENV=azure
```

Run it from an interactive terminal. `ENV=azure` runs the container with `-it` and passes
`--credit-prompts --repeat-first-config`, which does three things:

- **Before the run starts and after it ends**, the harness pauses and asks for **CPU Credits
  Remaining**. In the portal, open the server > **Monitoring > Metrics**, choose the metric
  **CPU Credits Remaining**, and enter the latest value and that data point's time. Microsoft
  documents this metric as displayed in five-minute batches, so the newest point can be up to
  about five minutes old. The answers are stored verbatim as "user-reported from Azure portal".
- **At the very end** it repeats Part B's first configuration (exact search) to detect CPU
  throttling.
- It times `SELECT 1` (500 round trips) at the start and end as a network baseline.

The same metric from the CLI, if you want to cross-check (not part of the recorded protocol):

```bash
SERVER_ID=$(az postgres flexible-server show --resource-group "$RG" --name "$SERVER" --query id -o tsv)
az monitor metrics list --resource "$SERVER_ID" --metrics cpu_credits_remaining \
  --aggregation Average --offset 1h -o table
```

## 7. Stop or delete when done

```bash
az postgres flexible-server stop --resource-group "$RG" --name "$SERVER"
az group delete --name "$RG"        # deletes the server and everything in the group
```

## What was checked against Microsoft documentation (2026-10-01)

Checked on Microsoft Learn on 2026-10-01:

- `az group create` (`--name`, `--location`) and `az group delete` (`--name`): CLI reference
  `az group`.
- `az postgres flexible-server create` flags `--resource-group`, `--name`, `--location`, `--tier`
  (Burstable/GeneralPurpose/MemoryOptimized), `--sku-name` (example `Standard_B1ms`),
  `--storage-size`, `--version` (16 accepted), `--zonal-resiliency` (Disabled/Enabled),
  `--storage-auto-grow`, `--admin-user`, `--admin-password`, `--public-access` (a single IP or
  range is accepted); `show`, `stop` and `start`: CLI reference `az postgres flexible-server`. The
  current CLI has `--zonal-resiliency`. There is no `--high-availability` flag in the current
  reference.
- `az postgres flexible-server firewall-rule create` (`--resource-group`, `--server-name`, `--name`,
  `--start-ip-address`, `--end-ip-address`) and `parameter set/show` (`--resource-group`,
  `--server-name`, `--name`, `--value`): their CLI reference pages.
- Allowlisting through `azure.extensions` (portal: **Settings > Parameters**, CLI command above):
  "Allow extensions in Azure Database for PostgreSQL flexible server".
- Metric display name **CPU Credits Remaining**, REST name `cpu_credits_remaining`, unit Count,
  Burstable tier, emitted every minute, displayed in five-minute batches (up to five minutes
  late): "Monitor using metrics and logs" and the Azure Monitor "Supported metrics -
  Microsoft.DBforPostgreSQL/flexibleServers" reference.
- `az monitor metrics list` flags `--resource`, `--metrics`, `--aggregation`, `--offset`: CLI
  reference `az monitor metrics`.
- B1ms is 1 vCore and 2 GiB, and burstable credits deplete under sustained CPU: "Compute options".

Not verified:

- **Storage performance tier.** The docs list `--performance-tier` but the reference page I read
  didn't show its accepted values or the default for 32 GiB. P4 / 120 IOPS is what the portal
  showed for this server, so the CLI command leaves the tier at its default instead of setting
  it. Check it in the portal after creating the server.
- **Exact portal labels and wizard layout** (for example "Workload type", "Configure server",
  "Server parameters" vs "Parameters"). Microsoft's extension page says **Settings >
  Parameters**. The portal changes often, so treat labels as approximate.
- **The B1ms CPU baseline percentage and credit accrual rate.** They aren't on the PostgreSQL
  compute page and weren't checked elsewhere.
- **The Azure for Students allowed-region list.** It comes from the subscription's policy as
  observed, not from Microsoft documentation.
- **`az monitor metrics list` time-window behavior.** The interval and offset formats were
  checked, but the command wasn't run against this server.
- **None of the `az` commands were executed in this session.** The server already existed. They
  are checked against the reference only.
