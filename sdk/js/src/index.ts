// Copyright 2026 Truthlocks Inc.
// Licensed under the Apache License, Version 2.0

export { MaipClient } from "./client.js";
export type { MaipClientOptions } from "./client.js";

export type {
  Agent,
  AgentStatus,
  Bundle,
  CheckGuardrailsRequest,
  ComputeTrustScoreRequest,
  CreateAgentRequest,
  CreateSessionRequest,
  Delegation,
  DelegationStatus,
  ExecuteOrchestrationRequest,
  GuardrailResult,
  GuardrailViolation,
  ListAgentsOptions,
  ListResponse,
  OfferDelegationRequest,
  Orchestration,
  OrchestrationStatus,
  Receipt,
  Scope,
  Session,
  SessionStatus,
  TrustFactor,
  TrustLevel,
  TrustScore,
} from "./types.js";

export { verifyBundle, verifyReceiptHash } from "./verify.js";
export type { VerifyBundleResult } from "./verify.js";

export {
  MaipError,
  LimitExceededError,
  UnauthorizedError,
  NotFoundError,
  VerificationError,
} from "./errors.js";
