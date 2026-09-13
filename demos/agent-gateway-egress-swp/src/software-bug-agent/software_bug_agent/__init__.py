# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ---------------------------------------------------------------------------
# Agent Gateway compatibility patches
#
# When a Reasoning Engine is bound to an Agent Gateway, ALL container egress
# enters the customer VPC via PSC-I. Several SDK calls fail because the
# container uses Google's *internal* DNS (not the customer VPC's Cloud DNS),
# so *.googleapis.com names resolve to Google-internal IPs that are not
# routable from the customer VPC.
#
# The customer VPC has private Cloud DNS zones that map *.googleapis.com to
# 199.36.153.8/30 (the private.googleapis.com VIP), plus a PBR that bypasses
# the SWP for that range so those calls exit via Private Google Access instead
# of Cloud NAT. But because the container ignores the VPC's Cloud DNS, those
# zones have no effect.
#
# Patch 1 — socket.getaddrinfo interception
# -----------------------------------------
# Intercept Python-level DNS resolution to redirect every *.googleapis.com
# hostname to 199.36.153.8 (private.googleapis.com VIP), replicating in
# userspace what the VPC Cloud DNS zones were supposed to do. This fixes:
#   - VertexAiSessionService (aiohttp) → us-central1-aiplatform.googleapis.com
#   - OTel OTLP exporter (requests) → telemetry.googleapis.com
#   - google-genai model calls → aiplatform.googleapis.com
# Traffic to non-googleapis.com hosts (e.g. *.run.app MCP server) is
# unaffected and continues through SWP → Cloud NAT (the CUJ2 mechanism).
# gRPC's native resolver calls libc getaddrinfo (not Python's), so gRPC is
# handled separately by GRPC_DNS_RESOLVER=native + SafeAdkApp.project_id().
#
# Patch 2 — _warn_if_telemetry_api_disabled no-op
# ------------------------------------------------
# Safety net for old pickles that still have enable_tracing=True. New pickles
# use SafeAdkApp (which never sets enable_tracing) so this branch is never
# reached, but it remains here to guard against transient scenarios.
#
# Patch 3 — AdkApp.project_id fallback
# -------------------------------------
# Safety net: if the monkey-patch here runs but SafeAdkApp's override does
# not (e.g. an old pickle), make project_id() return the project string from
# _tmpl_attrs rather than calling cloudresourcemanager.googleapis.com.
# ---------------------------------------------------------------------------

import os as _os
import re as _re
import socket as _socket

# Only apply the getaddrinfo redirect inside the RE container. The RE runtime
# sets GOOGLE_CLOUD_AGENT_ENGINE_ID; local builds (deploy_agent.py --build-only)
# do not have it, so the patch must not run there — 199.36.153.8 is only
# reachable via Private Google Access inside the customer VPC.
if _os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID"):
    _GOOGLEAPIS_RE = _re.compile(r'.*\.googleapis\.com$')
    _PGA_VIP = "199.36.153.8"
    _orig_getaddrinfo = _socket.getaddrinfo

    def _googleapis_getaddrinfo(host, port, *args, **kwargs):
        """Redirect *.googleapis.com DNS to 199.36.153.8 (private.googleapis.com VIP).

        The container's internal DNS returns Google-internal IPs for regional API
        endpoints (e.g. us-central1-aiplatform.googleapis.com) that are not
        routable from the customer VPC. Redirecting to 199.36.153.8 lets the VPC's
        PBR 1500 route those calls via Private Google Access, where Google's
        SNI-based routing dispatches them to the correct backend.
        """
        if isinstance(host, str) and _GOOGLEAPIS_RE.match(host):
            return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, '', (_PGA_VIP, port))]
        return _orig_getaddrinfo(host, port, *args, **kwargs)

    _socket.getaddrinfo = _googleapis_getaddrinfo

try:
    from vertexai.agent_engines.templates import adk as _adk_module

    _adk_module._warn_if_telemetry_api_disabled = lambda: None

    def _safe_project_id(self):
        import os
        return (
            self._tmpl_attrs.get("project")
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
        )

    _adk_module.AdkApp.project_id = _safe_project_id
except Exception:
    pass
