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
# Agent Gateway compatibility patch
#
# When a Reasoning Engine is bound to an Agent Gateway, ALL container egress
# enters the customer VPC via PSC-I. AdkApp.set_up() calls
# _warn_if_telemetry_api_disabled(), which POSTs to telemetry.googleapis.com
# — a Google-internal endpoint unreachable from customer VPCs even with
# Private Google Access. The call raises SSLEOFError, which surfaces as
# UserCodeControlPlaneError and prevents the engine from starting.
#
# This patch replaces the function with a no-op at import time.  It executes
# before set_up() is called (the agent source is installed from the
# dependencies bundle before the pickled AdkApp is loaded), so the guard in
# set_up():
#
#   if self._tmpl_attrs.get("enable_tracing"):
#       _warn_if_telemetry_api_disabled()
#
# ends up calling our no-op even when the pickle was built with
# enable_tracing=True.  New artifacts built from this source will not pass
# enable_tracing=True at all, making this patch doubly redundant — but it
# remains here as a safety net for any transient scenario where the old
# parameter surfaces.
# ---------------------------------------------------------------------------
try:
    from vertexai.agent_engines.templates import adk as _adk_module
    _adk_module._warn_if_telemetry_api_disabled = lambda: None

    # project_id() calls resource_manager_utils.get_project_id() via gRPC, which
    # uses the gRPC DirectPath/C2P resolver and tries both IPv6 DirectPath addresses
    # (2607:f8b0::/32, unreachable: VPC has no IPv6 routes) and IPv4 "240.0.0.2"
    # (Google internal backend, not routable from customer VPC). Catch all exceptions
    # and return the project string directly — the SDK accepts project strings (not
    # only numeric IDs) for OTel setup and session service initialization.
    _orig_project_id_fget = _adk_module.AdkApp.project_id.fget

    def _safe_project_id(self):
        import os
        project = self._tmpl_attrs.get("project") or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project:
            return None
        try:
            return _orig_project_id_fget(self)
        except Exception:
            return project

    _adk_module.AdkApp.project_id = property(_safe_project_id)
except Exception:
    pass
