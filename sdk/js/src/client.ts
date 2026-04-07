// Copyright 2026 Truthlocks Inc.
// Licensed under the Apache License, Version 2.0

import type {
  Agent,
  CheckGuardrailsRequest,
  ComputeTrustScoreRequest,
  CreateAgentRequest,
  CreateSessionRequest,
  Delegation,
  ExecuteOrchestrationRequest,
  GuardrailResult,
  ListAgentsOptions,
  ListResponse,
  OfferDelegationRequest,
  Orchestration,
  Session,
  TrustScore,
} from "./types.js";
import {
  LimitExceededError,
  MaipError,
  NotFoundError,
  UnauthorizedError,
} from "./errors.js";

const DEFAULT_BASE_URL = "https://api.truthlocks.com";

export interface MaipClientOptions {
  apiKey: string;
  baseUrl?: string;
  timeoutMs?: number;
}

export class MaipClient {
  private readonly apiKey: string;
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor(options: MaipClientOptions) {
    if (!options.apiKey) {
      throw new MaipError("apiKey is required");
    }
    this.apiKey = options.apiKey;
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.timeoutMs = options.timeoutMs ?? 30_000;
  }

  async registerAgent(request: CreateAgentRequest): Promise<Agent> {
    return this.post<Agent>("/v1/agents", request);
  }

  async listAgents(options?: ListAgentsOptions): Promise<ListResponse<Agent>> {
    const params = new URLSearchParams();
    if (options?.status) params.set("status", options.status);
    if (options?.offset !== undefined) params.set("offset", String(options.offset));
    if (options?.limit !== undefined) params.set("limit", String(options.limit));
    return this.get<ListResponse<Agent>>("/v1/agents", params);
  }

  async getAgent(agentId: string): Promise<Agent> {
    return this.get<Agent>("/v1/agents/" + encodeURIComponent(agentId));
  }

  async suspendAgent(agentId: string): Promise<Agent> {
    return this.post<Agent>("/v1/agents/" + encodeURIComponent(agentId) + "/suspend", {});
  }

  async revokeAgent(agentId: string): Promise<Agent> {
    return this.post<Agent>("/v1/agents/" + encodeURIComponent(agentId) + "/revoke", {});
  }

  async createSession(request: CreateSessionRequest): Promise<Session> {
    return this.post<Session>("/v1/sessions", request);
  }

  async terminateSession(sessionId: string): Promise<Session> {
    return this.post<Session>("/v1/sessions/" + encodeURIComponent(sessionId) + "/terminate", {});
  }

  async getTrustScore(agentId: string): Promise<TrustScore> {
    return this.get<TrustScore>("/v1/agents/" + encodeURIComponent(agentId) + "/trust-score");
  }

  async computeTrustScore(request: ComputeTrustScoreRequest): Promise<TrustScore> {
    return this.post<TrustScore>("/v1/agents/" + encodeURIComponent(request.agentId) + "/trust-score/compute", request);
  }

  async offerDelegation(request: OfferDelegationRequest): Promise<Delegation> {
    return this.post<Delegation>("/v1/delegations", request);
  }

  async acceptDelegation(delegationId: string): Promise<Delegation> {
    return this.post<Delegation>("/v1/delegations/" + encodeURIComponent(delegationId) + "/accept", {});
  }

  async executeOrchestration(request: ExecuteOrchestrationRequest): Promise<Orchestration> {
    return this.post<Orchestration>("/v1/orchestrations", request);
  }

  async checkGuardrails(request: CheckGuardrailsRequest): Promise<GuardrailResult> {
    return this.post<GuardrailResult>("/v1/guardrails/check", request);
  }

  private async get<T>(path: string, params?: URLSearchParams): Promise<T> {
    let url = this.baseUrl + path;
    if (params && params.toString()) {
      url += "?" + params.toString();
    }
    return this.request<T>("GET", url);
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>("POST", this.baseUrl + path, body);
  }

  private async request<T>(method: string, url: string, body?: unknown): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const headers: Record<string, string> = {
        Authorization: "Bearer " + this.apiKey,
        "Content-Type": "application/json",
        Accept: "application/json",
        "User-Agent": "@truthlocks/maip-sdk/0.1.0",
      };

      const init: RequestInit = { method, headers, signal: controller.signal };

      if (body !== undefined) {
        init.body = JSON.stringify(body);
      }

      const response = await fetch(url, init);

      if (!response.ok) {
        await this.handleErrorResponse(response);
      }

      return (await response.json()) as T;
    } catch (error) {
      if (error instanceof MaipError) throw error;
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new MaipError("Request timed out after " + this.timeoutMs + "ms");
      }
      throw new MaipError("Request failed: " + (error instanceof Error ? error.message : String(error)));
    } finally {
      clearTimeout(timeout);
    }
  }

  private async handleErrorResponse(response: Response): Promise<never> {
    let errorBody: { message?: string; code?: string } = {};
    try {
      errorBody = (await response.json()) as typeof errorBody;
    } catch {
      // Response body may not be JSON
    }

    const message = errorBody.message ?? "HTTP " + response.status;
    const code = errorBody.code;

    switch (response.status) {
      case 401:
        throw new UnauthorizedError(message);
      case 404:
        throw new NotFoundError("Resource", message);
      case 429: {
        const retryAfter = response.headers.get("Retry-After");
        throw new LimitExceededError(message, retryAfter ? parseInt(retryAfter, 10) : undefined);
      }
      default:
        throw new MaipError(message, response.status, code);
    }
  }
}
