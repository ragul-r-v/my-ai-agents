# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Wrapper to run agents-cli eval grade locally without GCP credentials."""

import sys

# Add agents-cli to sys.path
sys.path.append(
    r"C:\Users\Ragul\AppData\Roaming\uv\tools\google-agents-cli\Lib\site-packages"
)

# Mock google.auth.default to prevent vertexai client initialization errors
import google.auth
from google.auth.credentials import Credentials


class DummyCredentials(Credentials):
    def refresh(self, request):
        pass


google.auth.default = lambda *args, **kwargs: (DummyCredentials(), "dummy-project")

# Set system arguments
sys.argv = [
    "agents-cli",
    "eval",
    "grade",
    "--metrics",
    "routing_correctness,security_containment",
    "--config",
    "tests/eval/eval_config.yaml",
    "--traces",
    "artifacts/traces/generated_traces.json",
]

# Run the CLI main
from google.agents.cli.main import main  # noqa: E402

if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        if e.code != 0:
            sys.exit(e.code)
