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
# SafeAdkApp — AdkApp subclass that avoids network calls during set_up()
#
# When a Reasoning Engine is bound to an Agent Gateway, all container egress
# enters the customer VPC via PSC-I.  Two network calls in set_up() fail:
#
# 1. project_id() — calls resource_manager_utils.get_project_id() over gRPC
#    to cloudresourcemanager.googleapis.com.  The SWP is not a transparent
#    TCP proxy for gRPC, so this call fails.
#    Fix: override project_id() to return the string baked into the pickle.
#
# 2. VertexAiSessionService — AdkApp.set_up() instantiates this when
#    GOOGLE_CLOUD_AGENT_ENGINE_ID is in the environment (i.e. always in the
#    RE container).  It calls us-central1-aiplatform.googleapis.com via
#    aiohttp.  The RE container's internal DNS resolver returns a DirectPath
#    IP (240.x.x.x) for that regional endpoint; those IPs are not routable
#    from the customer VPC, so the connection fails with ENETUNREACH (or,
#    after the getaddrinfo patch redirects to 199.36.153.8, with a TLS
#    error because private.googleapis.com does not support that endpoint).
#    Fix: pass session_service_builder=InMemorySessionService so set_up()
#    never instantiates VertexAiSessionService.  Sessions are in-memory per
#    worker — sufficient for a demo where session persistence across RE
#    instances is not required.
#
# Similarly, memory_service_builder=InMemoryMemoryService avoids
# VertexAiMemoryBankService, which has the same network-unreachable problem.
#
# Why a subclass instead of a monkey-patch in __init__.py?
# The pickle references the class by its fully-qualified name
# (software_bug_agent.safe_adk.SafeAdkApp), so pickle deserialization
# imports THIS module — guaranteeing the override is active before
# set_up() is ever called.
# ---------------------------------------------------------------------------

from __future__ import annotations

import os
from typing import Any, Optional

try:
    from vertexai.agent_engines import AdkApp
except ImportError:
    from vertexai.preview.reasoning_engines import AdkApp  # type: ignore[no-redef]


class SafeAdkApp(AdkApp):
    """AdkApp subclass that avoids network calls during set_up()."""

    def __init__(self, **kwargs: Any) -> None:
        from google.adk.sessions.in_memory_session_service import InMemorySessionService
        from google.adk.memory.in_memory_memory_service import InMemoryMemoryService

        kwargs.setdefault("session_service_builder", InMemorySessionService)
        kwargs.setdefault("memory_service_builder", InMemoryMemoryService)
        super().__init__(**kwargs)

    def project_id(self) -> Optional[str]:
        return (
            self._tmpl_attrs.get("project")
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
        )
