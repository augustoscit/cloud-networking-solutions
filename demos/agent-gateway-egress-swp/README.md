# CUJ 2 — Agent Gateway: Public Egress via Secure Web Proxy + Cloud NAT Static IP

This demo shows how to govern all public-internet egress from a Vertex AI Agent
Runtime (Reasoning Engine) so that:

1. Every outbound connection from the agent exits **through the customer VPC**
   via the **Agent Gateway** (AGENT_TO_ANYWHERE mode, PSC-Interface).
2. That VPC-bound traffic is steered through a **customer-deployed Secure Web
   Proxy (SWP) in next-hop mode** for Layer-7 inspection and policy enforcement.
3. The SWP forwards to **Cloud NAT with a reserved static external IP**, giving
   the agent a predictable, allowlistable egress identity.

The agent (a software bug-triage assistant) reaches a public, no-auth **MCP
server on Cloud Run** to read bug tickets. The Cloud Run service sees the
agent's traffic arriving from the static NAT IP, which you can confirm in its
request logs.

---

## Architecture

### Traffic Path

The demo has **two distinct egress paths** from the Reasoning Engine:

```
┌──────────────────────────────────────────────────────────────────────┐
│  Google-managed (Vertex AI)                                          │
│                                                                      │
│   Reasoning Engine (Agent Runtime)                                   │
│     └─ agent_gateway_config bound → Agent Gateway (AGENT_TO_ANYWHERE)│
└──────────────────────────────────────────────────────────────────────┘
                              │ PSC-Interface network attachment
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│  Customer VPC                                                        │
│                                                                      │
│   [Agent Gateway subnet 10.20.0.0/26]  (Private Google Access ON)   │
│          │                                                           │
│    DNS?  │                                                           │
│   ┌──────┴──────────────────┐                                        │
│   │                         │                                        │
│   │ *.googleapis.com        │ all other traffic                      │
│   │ → DNS: 199.36.153.8/30  │ → DNS: public IP                       │
│   │                         │                                        │
│   │ PBR 1500: bypass SWP    │ PBR 2000: redirect to SWP              │
│   │ DEFAULT_ROUTING         │ next_hop_ilb_ip = SWP internal IP      │
│   │        │                │        │                               │
│   │        ▼                │        ▼                               │
│   │ Private Google Access   │ Secure Web Proxy (NEXT_HOP_MODE)       │
│   │ (internal, no NAT)      │   • ALLOW policy (no TLS inspection)   │
│   │        │                │   • Anti-loop PBR (priority 1000)      │
│   │        ▼                │        │                               │
│   │ Google APIs ✓           │        ▼                               │
│   │ (telemetry, Vertex AI,  │ Cloud Router → Cloud NAT               │
│   │  model endpoint, etc.)  │   • MANUAL_ONLY · static external IP   │
│   │                         │        │                               │
│   └─────────────────────────┘        │ Public internet               │
│                                      ▼                               │
└──────────────────────────── bug-tickets-mcp (Cloud Run) ─────────────┘
                                INGRESS_TRAFFIC_ALL · no IAM gate
                                (sees the static NAT IP as source)
```

> **Why two paths?** When a Reasoning Engine is bound to an Agent Gateway, ALL
> its outbound traffic enters the customer VPC via PSC-I. Internal Google API
> endpoints (`*.mtls.googleapis.com`, Vertex AI, Cloud Trace, etc.) can only
> be reached from within Google's infrastructure — routing them through Cloud NAT
> (a public IP) causes SSL handshake failures. The DNS override + PBR bypass
> routes Google API traffic via **Private Google Access** (internal, no NAT),
> while all other internet traffic (the MCP server) still goes through the
> SWP → Cloud NAT path where the static IP is enforced.

### Layer-by-Layer Reference Table

| Layer | What it does | Terraform resource |
|---|---|---|
| **Agent Runtime** | Hosts the ADK-based software-bug-agent; all connections egress through the Agent Gateway | `google_vertex_ai_reasoning_engine` in `modules/agent-engine/main.tf` |
| **Agent Gateway binding** | `agent_gateway_config.agent_to_anywhere_config.agent_gateway` routes ALL engine egress through the customer VPC | same resource, `agent_gateway_config` block |
| **PSC-Interface** | Dedicated network attachment connecting Agent Runtime to the customer VPC | `google_compute_network_attachment` in `modules/agent-gateway/main.tf` |
| **Agent Gateway** | `AGENT_TO_ANYWHERE` gateway terminates PSC-I and injects traffic into the Agent Gateway subnet | `google_network_services_agent_gateway` in `modules/agent-gateway/main.tf` |
| **Private Google Access** | Enabled on the Agent Gateway subnet so Google API traffic can exit internally without NAT | `private_ip_google_access = true` on `google_compute_subnetwork.agent_gateway` in `modules/networking/main.tf` |
| **DNS override (googleapis)** | Private Cloud DNS zones redirect `*.googleapis.com` and `*.mtls.googleapis.com` to the `private.googleapis.com` VIP (`199.36.153.8/30`) | `google_dns_managed_zone.googleapis_private` + `.mtls_googleapis_private` in `modules/networking/main.tf` |
| **Policy-Based Route (googleapis bypass)** | Priority 1500 — lets traffic destined for `199.36.153.8/30` and `199.36.153.4/30` take the default route (Private Google Access), bypassing the SWP | `google_network_connectivity_policy_based_route.googleapis_bypass` + `.googleapis_restricted_bypass` in `modules/secure-web-proxy/main.tf` |
| **Policy-Based Route (forced SWP)** | Priority 2000 — redirects all remaining Agent Gateway subnet egress (src `10.20.0.0/26`, dst `0.0.0.0/0`) to the SWP gateway IP | `google_network_connectivity_policy_based_route.agw_to_swp` in `modules/secure-web-proxy/main.tf` |
| **Policy-Based Route (anti-loop)** | Priority 1000 — prevents SWP's own proxy-originated connections from looping back through the SWP | `google_network_connectivity_policy_based_route.swp_anti_loop` in `modules/secure-web-proxy/main.tf` |
| **Secure Web Proxy** | L7 proxy in `NEXT_HOP_ROUTING_MODE`; applies `ALLOW` security policy; forwards traffic to the default internet route | `google_network_services_gateway` in `modules/secure-web-proxy/main.tf` |
| **Cloud NAT** | SNAT with a single reserved static external IP; the MCP server sees this IP | `google_compute_router_nat` + `google_compute_address.nat` in `modules/networking/main.tf` |
| **bug-tickets-mcp** | Public Cloud Run service (`INGRESS_TRAFFIC_ALL`); no IAP or auth; logs the caller's IP in `X-Forwarded-For` | `modules/mcp-cloud-run` + `images.tf` (Cloud Build from source) |

---

## Differences from `demos/agent-gateway`

| Feature | `demos/agent-gateway` (CUJ1) | This demo (CUJ2) |
|---|---|---|
| Focus | **Ingress** governance (IAP, Model Armor) | **Egress** governance (SWP, Cloud NAT static IP) |
| MCP server | Internal (private Cloud Run, IAP-gated) | Public (no-auth Cloud Run, `*.run.app`) |
| SWP | None | Customer-deployed, next-hop mode |
| Cloud NAT | AUTO_ONLY | MANUAL_ONLY with reserved static IP |
| Authz extensions | IAP + Model Armor | None (scope: network egress only) |

---

## Prerequisites

- A GCP project with billing enabled.
- Your account must have `roles/owner` or equivalent (`roles/editor` +
  `roles/iam.securityAdmin` + `roles/resourcemanager.projectIamAdmin`).
- Tools: `gcloud` (authenticated), `terraform >= 1.5`, `uv` (Python package manager).
- The project must be under a GCP **organization** (required for Agent Identity
  IAM principal sets).

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

---

## Deploy Walkthrough

### Step 0 — Clone and navigate

```bash
cd cloud-networking-solutions/demos/agent-gateway-egress-swp/terraform
```

### Step 1 — Create the Terraform state bucket

```bash
export PROJECT_ID=$(gcloud config get-value project)
export REGION=us-central1

gcloud storage buckets create "gs://${PROJECT_ID}-tfstate" \
  --location="${REGION}" \
  --uniform-bucket-level-access
```

### Step 2 — Configure Terraform

```bash
cp example.backend.conf backend.conf
# Edit backend.conf: set bucket = "${PROJECT_ID}-tfstate"

cp example.tfvars terraform.tfvars
# Edit terraform.tfvars:
#   project_id      = "YOUR_PROJECT_ID"
#   organization_id = "YOUR_ORG_NUMERIC_ID"   # gcloud organizations list
#   region          = "us-central1"
```

Get the numeric org ID:
```bash
gcloud organizations list
```

### Step 3 — Phase 1 apply (infrastructure + MCP server)

This creates all networking, SWP, Cloud NAT, the Agent Gateway, and the
bug-tickets-mcp Cloud Run service. The Reasoning Engine is NOT created yet
(`deploy_reasoning_engine` defaults to `false`).

```bash
terraform init -backend-config=backend.conf
terraform plan
terraform apply
```

After apply, note these outputs:
```bash
terraform output nat_static_ip          # The IP the MCP server will see
terraform output bug_tickets_mcp_url    # URL used in deploy_agent.py
terraform output agent_gateway_id       # Used in --agent-gateway flag
```

### Step 4 — Build and stage agent artifacts

From the agent source directory, build the artifact bundle and write the
manifest that Terraform will reference in Phase 2.

```bash
cd ../src/software-bug-agent

# Install dependencies (uv will create a venv automatically)
uv sync

# Stage agent artifacts to GCS and write build/agent_artifacts.json
uv run python deploy_agent.py \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --mcp-url="$(cd ../../terraform && terraform output -raw bug_tickets_mcp_url)" \
  --build-only
```

The manifest is written to `../../build/agent_artifacts.json` (relative to this
directory), which is the path `terraform/main.tf` expects by default.

### Step 5 — Phase 2 apply (Reasoning Engine)

```bash
cd ../../terraform

terraform apply -var deploy_reasoning_engine=true
```

This creates the `google_vertex_ai_reasoning_engine` with
`agent_gateway_config.agent_to_anywhere_config.agent_gateway` bound, so ALL
agent egress flows through the VPC → SWP → Cloud NAT path.

```bash
terraform output reasoning_engine_name  # full resource ID
```

---

## Verification

### 1. Confirm the static NAT IP

The reserved external IP is visible in the GCP Console:
**VPC Network > IP addresses > External IP addresses** — look for the address
named `<name_prefix>-nat-ip`.

```bash
terraform output nat_static_ip
```

### 2. Send a test query to the agent

Go to **Vertex AI > Agent Engine** in the GCP Console, select the deployed
Reasoning Engine, and click **Test**. Send a prompt like:

```
List all open P0 bugs assigned to alice@quantumroast.example.com.
```

The agent will call `list_tickets` via MCPToolset, which makes an HTTP request
from the Reasoning Engine container — through the Agent Gateway, the SWP, and
Cloud NAT — to the Cloud Run MCP server.

### 3. Verify the egress IP in Cloud Run logs

The bug-tickets-mcp Cloud Run service logs every request. Check for the
`X-Forwarded-For` header:

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="bug-tickets-mcp" AND textPayload:"GET /mcp"' \
  --project="${PROJECT_ID}" \
  --limit=10 \
  --format="value(textPayload)"
```

You should see the static NAT IP (from `terraform output nat_static_ip`) in the
logged request source or `X-Forwarded-For`. If the IP matches, the egress path
is confirmed end-to-end.

### 4. Inspect SWP logs (optional)

The Secure Web Proxy writes access logs to Cloud Logging under
`resource.type="networksecurity.googleapis.com/GatewaySecurityPolicy"`. You can
inspect which sessions passed through:

```bash
gcloud logging read \
  'resource.type="networksecurity.googleapis.com/GatewaySecurityPolicy"' \
  --project="${PROJECT_ID}" \
  --limit=20 \
  --format="json"
```

---

## Known Caveats and Troubleshooting

### One Reasoning Engine per Agent Gateway per region

Agent Gateway currently supports **one bound Reasoning Engine per region per
gateway**. Attempting to bind a second engine to the same gateway in the same
region will fail. Use a separate gateway (or a separate project) if you need
multiple engines.

### The Agent Gateway has its own internal proxy

The Agent Gateway (`google_network_services_agent_gateway`) runs a
Google-managed internal SWP as part of its control plane. This is separate from
the **customer-deployed SWP** this demo provisions in `modules/secure-web-proxy`.
Do not confuse the two: the customer SWP is the one enforcing your security
policy and the one visible in your VPC's policy-based routes.

### SWP auto-creates a hidden Cloud Router

When the `google_network_services_gateway` (SWP) is created, GCP automatically
provisions a Cloud Router for the SWP's own proxy-originated egress. This
hidden router is separate from the explicit Cloud Router created by the
`networking` module for Cloud NAT. Both routers coexist in the same VPC and
region without conflict. `delete_swg_autogen_router_on_destroy = true` is set in
the SWP module to clean up the hidden router on `terraform destroy`.

If you see an unexpected Cloud Router in the Console (named something like
`swg-autogen-router-...`), this is it — leave it alone.

### Google API calls require Private Google Access + DNS override

When a Reasoning Engine is bound to an Agent Gateway, **all** its outbound
traffic enters the customer VPC via PSC-I. Without additional configuration,
internal Google endpoints like `telemetry.mtls.googleapis.com` (used by the
Vertex AI SDK for Cloud Trace during `set_up()`) would be routed through the
SWP → Cloud NAT path (public IP). Those `*.mtls.googleapis.com` endpoints only
accept connections from within Google's infrastructure — accessing them from a
public IP causes `SSLEOFError: UNEXPECTED_EOF_WHILE_READING`, which surfaces
as a `UserCodeControlPlaneError` and prevents the Reasoning Engine from starting.

This demo addresses the issue with four complementary measures:

1. **`GOOGLE_API_USE_MTLS_ENDPOINT = "never"`** — set as an env var on the
   Reasoning Engine. This is the primary fix: it forces the Vertex AI SDK to
   use `*.googleapis.com` (standard HTTPS) instead of `*.mtls.googleapis.com`
   (Google-internal mTLS, not accessible from customer VPCs even via PGA).
2. `private_ip_google_access = true` on the Agent Gateway subnet — enables
   Private Google Access so the subnet can reach Google APIs internally.
3. **Private Cloud DNS zones** — override `*.googleapis.com` and
   `*.mtls.googleapis.com` to resolve to the `private.googleapis.com` VIP
   (`199.36.153.8/30`) instead of their public IPs. This ensures that even if
   the SDK temporarily uses an mTLS variant hostname, traffic is still routed
   to the private VIP.
4. **PBRs at priority 1500** — route traffic destined for `199.36.153.8/30`
   (and `199.36.153.4/30`) via `DEFAULT_ROUTING`, bypassing the SWP. This means
   Google API calls exit via PGA (internal, no NAT), while all other internet
   traffic continues through the SWP → Cloud NAT path.

**Why `GOOGLE_API_USE_MTLS_ENDPOINT = "never"` is necessary**: The
`*.mtls.googleapis.com` endpoints use Google's internal service-mesh mTLS
protocol, which is fundamentally different from standard client-side mTLS. Even
when you point DNS at `private.googleapis.com` (199.36.153.8/30) and route
via PGA, the `private.googleapis.com` VIP handles standard HTTPS calls — not
the internal mTLS protocol. This results in `ConnectionResetError: Connection
reset by peer` from the VIP. The `GOOGLE_API_USE_MTLS_ENDPOINT = "never"` env
var prevents the SDK from attempting `*.mtls.googleapis.com` at all.

If you ever see the Reasoning Engine failing with SSL or connection errors during
`set_up()`, verify that:
- `GOOGLE_API_USE_MTLS_ENDPOINT = "never"` is set on the Reasoning Engine env vars
- The Agent Gateway subnet has `PRIVATE_IP_GOOGLE_ACCESS = True` (`gcloud compute networks subnets describe`)
- The DNS zones exist (`gcloud dns managed-zones list`)
- The bypass PBRs exist (`gcloud network-connectivity policy-based-routes list`)

### PSC-I subnet must be /26 or larger

The Agent Gateway subnet (`agent_gateway_subnet_cidr`, default `10.20.0.0/26`)
must be **/26 or larger**. A /28 is too small for PSC-Interface to allocate
endpoints. If you change the default, do not use a prefix length larger than 26
(e.g. /27, /28).

### Only one ACTIVE REGIONAL_MANAGED_PROXY subnet per region per VPC

GCP allows only one `ACTIVE` `REGIONAL_MANAGED_PROXY` subnet per VPC per
region. The `networking` module intentionally does **not** create a proxy-only
subnet; the `secure-web-proxy` module owns the single proxy-only subnet
(`swp_proxy_subnet_cidr`, default `10.30.0.0/24`). If you bring an existing VPC
that already has an ACTIVE REGIONAL_MANAGED_PROXY subnet, you must either remove
it or change its role to BACKUP before applying this Terraform.

### Policy-based routes and VM tags

Policy-based routes in this demo are scoped by **`src_range`** (the Agent
Gateway subnet CIDR), not by VM tags. This is correct: PSC-Interface traffic
does not carry VM tags, so `virtual_machine.tags` cannot be used to match it.

### terraform destroy — drain the PSC-I network attachment first

The Agent Gateway module includes a destroy-time drain gate
(`terraform_data.network_attachment_drain`) that polls for active PSC-I
connections before allowing the attachment to be deleted. If `terraform destroy`
appears to hang on the agent-gateway module, wait for active agent sessions to
close (or stop the Reasoning Engine first from the GCP Console / API), then
re-run.

The safe destroy order is:
1. Delete the Reasoning Engine from the GCP Console (Vertex AI > Agent Engine).
2. Run `terraform destroy`.

---

## Cleanup

```bash
# 1. Delete the Reasoning Engine first (avoids the drain-gate timeout)
#    Go to: Vertex AI > Agent Engine > select the engine > Delete

# 2. Destroy all Terraform-managed resources
cd terraform
terraform destroy

# 3. (Optional) Delete the state bucket
gcloud storage rm -r "gs://${PROJECT_ID}-tfstate"
```

---

## Extension Points

This demo is intentionally scoped to network egress governance. The following
features are out of scope but are natural next steps:

| Extension | Where to look |
|---|---|
| **Ingress governance** (IAP + Model Armor on the agent's endpoint) | `demos/agent-gateway` (CUJ1) |
| **TLS inspection in SWP** | Add `tls_inspect = true` + `certificate_urls` to `modules/secure-web-proxy/main.tf`; provision a Certificate Manager certificate authority pool |
| **URL filtering / deny rules in SWP** | Add additional `google_network_security_gateway_security_policy_rule` resources with `session_matcher` CEL expressions |
| **VPC Service Controls perimeter** | Wrap the project in a VPC-SC perimeter; the static NAT IP can be used in an egress rule to permit traffic to the MCP server's IP range |
| **Multiple agents / gateways** | Provision one `agent-gateway` module instance per agent per region; bind each Reasoning Engine to its dedicated gateway |
