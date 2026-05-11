/**
 * Truthlock SDK - Core Client
 *
 * The main entry point for interacting with the Truthlock API.
 *
 * @example
 * ```typescript
 * import { TruthlockClient } from '@truthlock/sdk';
 *
 * const client = new TruthlockClient({
 *   baseUrl: 'https://api.truthlocks.com',
 *   auth: { type: 'tenant', tenantId: 'your-tenant-id' }
 * });
 *
 * // Create an issuer
 * const issuer = await client.issuers.create({
 *   name: 'My Organization',
 *   legal_name: 'My Organization Inc.',
 *   display_name: 'My Org'
 * });
 * ```
 */

import type { TruthlockClientConfig, AuthStrategy } from "./types/models";
import {
  TruthlockError,
  NetworkError,
  RetryExhaustedError,
} from "./types/errors";
import {
  generateIdempotencyKey,
  sleep,
  calculateBackoff,
  redactSensitive,
} from "./utils";
import { IssuersResource } from "./resources/issuers";
import { KeysResource } from "./resources/keys";
import { AttestationsResource } from "./resources/attestations";
import { VerifyResource } from "./resources/verify";
import { AuditResource } from "./resources/audit";
import { ReceiptsResource } from "./resources/receipts";

export class TruthlockClient {
  private readonly baseUrl: string;
  private readonly auth: AuthStrategy;
  private readonly autoRetry: boolean;
  private readonly maxRetries: number;
  private readonly debug: boolean;
  private readonly fetchFn: typeof fetch;

  /** Issuer management operations */
  readonly issuers: IssuersResource;
  /** Key management operations */
  readonly keys: KeysResource;
  /** Attestation operations */
  readonly attestations: AttestationsResource;
  /** Verification operations */
  readonly verify: VerifyResource;
  /** Audit operations */
  readonly audit: AuditResource;
  /** Receipt operations (Ticket 81) */
  readonly receipts: ReceiptsResource;

  constructor(config: TruthlockClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, "");
    this.auth = config.auth;
    this.autoRetry = config.autoRetry ?? true;
    this.maxRetries = config.maxRetries ?? 3;
    this.debug = config.debug ?? false;
    this.fetchFn = config.fetch ?? globalThis.fetch;

    // Initialize resource classes
    this.issuers = new IssuersResource(this);
    this.keys = new KeysResource(this);
    this.attestations = new AttestationsResource(this);
    this.verify = new VerifyResource(this);
    this.audit = new AuditResource(this);
    this.receipts = new ReceiptsResource(this);
  }

  /**
   * Make an authenticated HTTP request to the Truthlock API.
   * Handles idempotency, retries, and error mapping automatically.
   */
  async request<T>(
    method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH",
    path: string,
    options?: {
      body?: unknown;
      idempotencyKey?: string;
      query?: Record<string, string | number | undefined>;
      skipRetry?: boolean;
      responseType?: "json" | "arraybuffer";
    },
  ): Promise<T> {
    const url = this.buildUrl(path, options?.query);
    const headers = this.buildHeaders(method, options?.idempotencyKey);

    const requestInit: RequestInit = {
      method,
      headers,
    };

    if (options?.body && method !== "GET") {
      requestInit.body = JSON.stringify(options.body);
    }

    this.log("request", method, url, options?.body);

    // Determine if this request is safe to retry
    const isIdempotent = method === "GET" || !!options?.idempotencyKey;
    const shouldRetry = this.autoRetry && isIdempotent && !options?.skipRetry;

    const responseType = options?.responseType || "json";

    if (shouldRetry) {
      return this.requestWithRetry<T>(
        url,
        requestInit,
        this.maxRetries,
        responseType,
      );
    }

    return this.executeRequest<T>(url, requestInit, responseType);
  }

  private async requestWithRetry<T>(
    url: string,
    init: RequestInit,
    maxAttempts: number,
    responseType: "json" | "arraybuffer" = "json",
  ): Promise<T> {
    let lastError: Error | undefined;

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        return await this.executeRequest<T>(url, init, responseType);
      } catch (error) {
        lastError = error instanceof Error ? error : new Error(String(error));

        // Don't retry client errors (4xx) except for rate limiting and specific retryable errors
        if (error instanceof TruthlockError) {
          const status = error.status ?? 0;
          if (status >= 400 && status < 500 && status !== 429) {
            throw error;
          }
        }

        if (attempt < maxAttempts - 1) {
          const delay = calculateBackoff(attempt);
          this.log(
            "retry",
            `Attempt ${attempt + 1} failed, retrying in ${delay}ms`,
          );
          await sleep(delay);
        }
      }
    }

    throw new RetryExhaustedError(
      `Request failed after ${maxAttempts} attempts`,
      maxAttempts,
      lastError,
    );
  }

  private async executeRequest<T>(
    url: string,
    init: RequestInit,
    responseType: "json" | "arraybuffer" = "json",
  ): Promise<T> {
    let response: Response;

    try {
      response = await this.fetchFn(url, init);
    } catch (error) {
      throw new NetworkError(
        `Network request failed: ${error instanceof Error ? error.message : "Unknown error"}`,
        error instanceof Error ? error : undefined,
      );
    }

    if (!response.ok) {
      const text = await response.text();
      let json: unknown;
      try {
        json = text ? JSON.parse(text) : null;
      } catch {
        json = null;
      }
      this.log("response", response.status, json || text);
      if (json && typeof json === "object") {
        throw TruthlockError.fromApiResponse({
          ...(json as Record<string, unknown>),
          status: response.status,
        });
      }
      throw new TruthlockError(
        text || `HTTP ${response.status}`,
        "HTTP_ERROR",
        { status: response.status },
      );
    }

    if (responseType === "arraybuffer") {
      this.log("response", response.status, "[binary]");
      return (await response.arrayBuffer()) as T;
    }

    const text = await response.text();
    let json: unknown;
    try {
      json = text ? JSON.parse(text) : null;
    } catch {
      json = null;
    }
    this.log("response", response.status, json || text);
    return json as T;
  }

  private buildUrl(
    path: string,
    query?: Record<string, string | number | undefined>,
  ): string {
    const url = new URL(path.startsWith("/") ? path : `/${path}`, this.baseUrl);

    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined) {
          url.searchParams.set(key, String(value));
        }
      }
    }

    return url.toString();
  }

  private buildHeaders(
    method: string,
    idempotencyKey?: string,
  ): Record<string, string> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };

    // Add authentication headers
    switch (this.auth.type) {
      case "tenant":
        headers["X-Tenant-ID"] = this.auth.tenantId;
        break;
      case "bearer":
        headers["Authorization"] = `Bearer ${this.auth.token}`;
        if (this.auth.tenantId) {
          headers["X-Tenant-ID"] = this.auth.tenantId;
        }
        break;
      case "service":
        headers["X-API-Key"] = this.auth.apiKey;
        if (this.auth.tenantId) {
          headers["X-Tenant-ID"] = this.auth.tenantId;
        }
        break;
    }

    // Add idempotency key for mutating operations
    if (method === "POST" || method === "PUT") {
      headers["Idempotency-Key"] = idempotencyKey || generateIdempotencyKey();
    }

    return headers;
  }

  private log(type: string, ...args: unknown[]): void {
    if (!this.debug) return;

    const redacted = args.map((arg) =>
      typeof arg === "object" && arg !== null
        ? redactSensitive(arg as Record<string, unknown>)
        : arg,
    );

    console.log(`[Truthlock SDK] ${type}:`, ...redacted);
  }
}
