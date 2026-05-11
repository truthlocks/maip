/**
 * Truthlock SDK - Main Entry Point
 *
 * Official TypeScript/JavaScript SDK for the Truthlock platform.
 * Provides type-safe access to all Truthlock APIs with automatic
 * authentication, idempotency, and retry handling.
 *
 * @packageDocumentation
 *
 * @example
 * ```typescript
 * import { TruthlockClient, Algorithm, Verdict } from '@truthlock/sdk';
 *
 * // Create client
 * const client = new TruthlockClient({
 *   baseUrl: 'https://api.truthlocks.com',
 *   auth: { type: 'tenant', tenantId: 'your-tenant-id' }
 * });
 *
 * // Create issuer and register key
 * const issuer = await client.issuers.create({
 *   name: 'My Org',
 *   legal_name: 'My Organization Inc.',
 *   display_name: 'My Org'
 * });
 *
 * await client.issuers.trust(issuer.id);
 *
 * await client.keys.register(issuer.id, {
 *   kid: 'key-1',
 *   alg: Algorithm.Ed25519,
 *   public_key_b64url: 'your-public-key'
 * });
 *
 * // Mint attestation
 * const attestation = await client.attestations.mint({
 *   issuer_id: issuer.id,
 *   kid: 'key-1',
 *   alg: Algorithm.Ed25519,
 *   payload_b64url: Buffer.from('Hello World').toString('base64url')
 * });
 *
 * // Verify
 * const result = await client.verify.verifyOnline({
 *   attestation_id: attestation.attestation_id,
 *   payload_b64url: Buffer.from('Hello World').toString('base64url')
 * });
 *
 * if (result.verdict === Verdict.Valid) {
 *   console.log('✓ Document verified successfully');
 * }
 * ```
 */

// Main client
export { TruthlockClient } from "./client";

// Types
export * from "./types/enums";
export * from "./types/models";
export * from "./types/errors";

// Resources
export { RiskResource } from "./resources/risk";
export type {
  IngestSignalRequest,
  EvaluateRiskRequest,
  RiskDecision,
  ATOEvaluateRequest,
  CreateCaseRequest,
} from "./resources/risk";

// Utilities
export {
  base64UrlEncode,
  base64UrlDecode,
  generateIdempotencyKey,
} from "./utils";
