# Copyright 2026 Truthlocks Inc. — Apache 2.0
"""Truthlocks MAIP wrapper for AWS Bedrock.

Usage::

    import boto3
    from truthlocks_bedrock import MAIPBedrockWrapper
    bedrock = boto3.client("bedrock-runtime")
    wrapper = MAIPBedrockWrapper(client=bedrock)
    response, receipt = wrapper.invoke_model(
        modelId="anthropic.claude-3-sonnet-20240229-v1:0",
        body='{"messages": [{"role": "user", "content": "Hello"}]}',
    )
"""

__version__ = "1.1.0"

from maip_ai_connectors.providers.bedrock import MAIPBedrockWrapper

__all__ = ["MAIPBedrockWrapper"]
