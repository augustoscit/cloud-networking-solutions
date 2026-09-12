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
# SafeAdkApp — AdkApp subclass that avoids gRPC calls during set_up()
#
# When a Reasoning Engine is bound to an Agent Gateway, all container egress
# enters the customer VPC via PSC-I.  AdkApp.set_up() calls self.project_id,
# which invokes resource_manager_utils.get_project_id() over gRPC to
# cloudresourcemanager.googleapis.com.  With GRPC_DNS_RESOLVER=native the
# container resolves that hostname to a real public Google IP (~173.194.x.x),
# which is then routed through the Secure Web Proxy — and the gRPC/TLS
# handshake fails because the SWP is not a transparent TCP proxy for gRPC.
#
# The project ID string is already baked into the pickle at build time
# (stored in self._tmpl_attrs["project"] by AdkApp.__init__).  The OTel
# instrumentor only needs a project identifier string — it does NOT require
# the numeric project number that get_project_id() would return.  So we
# override project_id to return the stored string directly.
#
# Why a subclass instead of a monkey-patch in __init__.py?
# The pickle references the class by its fully-qualified name
# (software_bug_agent.safe_adk.SafeAdkApp), so pickle deserialization
# imports THIS module — guaranteeing the override is active before
# set_up() is ever called.  A monkey-patch in __init__.py is not reliable
# because software_bug_agent is not imported during plain AdkApp unpickling.
# ---------------------------------------------------------------------------

from __future__ import annotations

import os
from typing import Optional

try:
    from vertexai.agent_engines import AdkApp
except ImportError:
    from vertexai.preview.reasoning_engines import AdkApp  # type: ignore[no-redef]


class SafeAdkApp(AdkApp):
    """AdkApp subclass with a network-free project_id() implementation."""

    def project_id(self) -> Optional[str]:
        return (
            self._tmpl_attrs.get("project")
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
        )
