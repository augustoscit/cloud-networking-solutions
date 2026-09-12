# software-bug-agent

ADK-based software bug-triage agent for the QuantumRoast dataset.
Part of the CUJ2 egress demo: agent reaches the `bug-tickets-mcp` Cloud Run
service via Agent Gateway → Secure Web Proxy → Cloud NAT with a static IP.

## Tools

| Tool | Source | Description |
|---|---|---|
| `get_current_date` | local | Returns today's date |
| `search_tool` | Google Search (AgentTool) | Looks up CVEs, advisories, community reports |
| `list_tickets` / `get_ticket` / `search_tickets` | MCP (`bug-tickets-mcp`) | Reads the in-memory QuantumRoast bug-ticket database |

## Local development

```bash
# Install dependencies
uv sync

# Set environment variables
cp .env.example .env
# Edit .env: set GOOGLE_CLOUD_PROJECT, BUG_TICKETS_MCP_URL

# Start the MCP server (separate terminal)
cd ../bug-tickets-mcp
uv run python server.py   # or: pip install fastmcp && python server.py

# Run the agent locally
uv run adk run software_bug_agent
```

## Deployment

See the top-level [README](../../README.md) for the full two-phase Terraform deploy walkthrough.

```bash
# Phase 1: build and stage artifacts (run after terraform apply phase 1)
uv run python deploy_agent.py \
  --project=YOUR_PROJECT \
  --region=us-central1 \
  --mcp-url=$(cd ../../terraform && terraform output -raw bug_tickets_mcp_url) \
  --build-only

# Phase 2: create the Reasoning Engine
cd ../../terraform
terraform apply -var deploy_reasoning_engine=true
```
