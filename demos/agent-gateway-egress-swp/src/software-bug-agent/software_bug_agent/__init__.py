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
