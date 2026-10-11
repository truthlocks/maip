# Copyright 2026 Truthlocks Inc.
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

"""Direct model provider integrations for MAIP receipt generation."""

from importlib import import_module


def __getattr__(name: str):
    """Load only the selected provider's optional dependencies."""
    modules = {
        "MAIPAnthropicWrapper": "anthropic",
        "MAIPBedrockWrapper": "bedrock",
        "MAIPOpenAIWrapper": "openai",
    }
    if name not in modules:
        raise AttributeError(name)
    return getattr(import_module(f"{__name__}.{modules[name]}"), name)

__all__ = [
    "MAIPAnthropicWrapper",
    "MAIPBedrockWrapper",
    "MAIPOpenAIWrapper",
]
