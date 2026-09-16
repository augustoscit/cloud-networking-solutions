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
# so *.googleapis.com names resolve to Google-internal DirectPath IPs
# (240.0.0.x) that are not routable from the customer VPC.
#
# Patch 1 — socket.getaddrinfo interception
# -----------------------------------------
# Intercepts Python-level DNS resolution to redirect every *.googleapis.com
# and *.run.app hostname to the actual public anycast IPs, obtained via DNS-over-HTTPS to
# Google's public resolver (8.8.8.8:443).
#
# Why not redirect to 199.36.153.8 (private.googleapis.com)?
# private.googleapis.com is a Private Google Access VIP that is only reachable
# from within Google's backbone network via PGA routing. Traffic from the
# Agent Gateway PSC-I that exits via Cloud NAT acquires a public source IP,
# which cannot reach 199.36.153.8 (the VIP drops such connections at TLS
# handshake). The public anycast IPs (172.217.x.x) serve the same Google APIs
# and accept connections from any IP — traffic flows: RE container → Agent
# Gateway PSC-I → SWP → Cloud NAT → 136.65.25.222 → 172.217.x.x (Vertex AI).
#
# The DoH query itself goes through SWP → Cloud NAT → 8.8.8.8 (ALLOW policy).
# If DoH fails (network not yet ready at import time), hardcoded stable IPs
# serve as the fallback.
#
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
# do not have it, so the patch must not run there.
if _os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID"):
    _GOOGLEAPIS_RE = _re.compile(r'.*\.(googleapis\.com|run\.app)$')
    _orig_getaddrinfo = _socket.getaddrinfo

    _DNS_CACHE = {}

    def _resolve_via_doh(host):
        """Resolve public IPs via DoH to 8.8.8.8:443 and cache the result."""
        if host in _DNS_CACHE:
            return _DNS_CACHE[host]

        import urllib.request as _req
        import json as _json
        _FALLBACK = ["172.217.112.4", "172.217.113.4", "172.217.114.4",
                     "172.217.115.4", "172.217.116.4"] if host.endswith(".googleapis.com") else []
        try:
            url = f"https://8.8.8.8/resolve?name={host}&type=A"
            r = _req.Request(url, headers={"Accept": "application/dns-json"})
            with _req.urlopen(r, timeout=5) as resp:
                data = _json.loads(resp.read())
                ips = [a["data"] for a in data.get("Answer", []) if a.get("type") == 1]
                if ips:
                    _DNS_CACHE[host] = ips
                    return ips
                return _FALLBACK
        except Exception:
            return _FALLBACK

    def _googleapis_getaddrinfo(host, port, *args, **kwargs):
        """Redirect *.googleapis.com and *.run.app DNS to public anycast IPs resolved via DoH.

        The container's built-in DNS returns DirectPath IPs (240.x.x.x) for
        *.googleapis.com and may fail for *.run.app. Those IPs are not routable
        from the customer VPC. Redirecting to the real public IPs allows traffic
        to flow via Agent Gateway PSC-I → SWP → Cloud NAT.
        """
        if isinstance(host, str) and _GOOGLEAPIS_RE.match(host):
            ips = _resolve_via_doh(host)
            if ips:
                return [
                    (_socket.AF_INET, _socket.SOCK_STREAM, 6, "", (ip, port))
                    for ip in ips
                ]
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
