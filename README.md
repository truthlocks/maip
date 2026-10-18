# Truthlocks MAIP integrations

Create signed evidence for AI operations and data pipelines using registered Truthlocks machine identities.

## Try a signed receipt without an account

[Run the reproducible receipt walkthrough](examples/developer-validation/README.md): verify a signature, deliberately alter the action, corrupt the signature and substitute a key. Uses Node.js built-ins and synthetic public data in the current hosted receipt/v2 signing format. No credentials, signup or telemetry. This does not establish hosted lifecycle checks or transparency inclusion.

We welcome external developer trials and sanitized bug reports. See the walkthrough for a separate hosted sandbox path and its limits.

## Install

```sh
python -m pip install maip-ai-connectors
# Add the integration used by your application:
python -m pip install truthlocks-langchain
```

Create a workspace at [Truthlocks Console](https://console.truthlocks.com), register an agent, and configure `MAIP_API_KEY` and `MAIP_AGENT_ID`. Provider credentials are separate. Read each integration's README for a complete local example, hosted submission, verification and delivery behavior.

## Integration source and guides

- [maip-ai-connectors](integrations/maip-ai-connectors/README.md)
- [dvc-maip](integrations/dvc-maip/README.md)
- [mlflow-maip](integrations/mlflow-maip/README.md)
- [delta-lake-maip](integrations/delta-lake-maip/README.md)
- [truthlocks-anthropic](integrations/truthlocks-anthropic/README.md)
- [truthlocks-autogen](integrations/truthlocks-autogen/README.md)
- [truthlocks-bedrock](integrations/truthlocks-bedrock/README.md)
- [truthlocks-crewai](integrations/truthlocks-crewai/README.md)
- [truthlocks-langchain](integrations/truthlocks-langchain/README.md)
- [truthlocks-llamaindex](integrations/truthlocks-llamaindex/README.md)
- [truthlocks-openai](integrations/truthlocks-openai/README.md)

## Receipt guarantees

Version 1.1.0 clients use `/v1/agent-receipts` and verify server signatures through `/v1/agent-receipts/verify/{receiptID}`. Signed metadata, server receipt IDs and local payload hashes are distinct. Verification includes lifecycle checks but does not establish transparency-log inclusion. Await asynchronous delivery before shutdown; writes are not automatically replayed.

The `reference`, `spec`, `sdk` and `verifier` directories contain the earlier protocol/reference implementation. They are not the hosted API contract for these integrations. Use the integration guides and [current API documentation](https://docs.truthlocks.com) for hosted requests.

## Development

Install a package's `dev` extras and run its tests from that package directory. HTTP fixtures cover failure handling; recorded release checks distinguish live receipt API tests from local framework/provider simulations. Never commit credentials or customer records.

Apache-2.0; see [LICENSE](LICENSE).
