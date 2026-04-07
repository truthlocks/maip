// Copyright 2026 Truthlocks Inc.
// Licensed under the Apache License, Version 2.0

/**
 * Base error class for all MAIP SDK errors.
 */
export class MaipError extends Error {
  /** HTTP status code, if the error originated from an API response. */
  public readonly statusCode?: number;

  /** Machine-readable error code from the API. */
  public readonly code?: string;

  constructor(message: string, statusCode?: number, code?: string) {
    super(message);
    this.name = "MaipError";
    this.statusCode = statusCode;
    this.code = code;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Thrown when the caller exceeds a rate limit or quota.
 */
export class LimitExceededError extends MaipError {
  /** Seconds until the limit resets. */
  public readonly retryAfterSeconds?: number;

  constructor(message: string, retryAfterSeconds?: number) {
    super(message, 429, "LIMIT_EXCEEDED");
    this.name = "LimitExceededError";
    this.retryAfterSeconds = retryAfterSeconds;
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Thrown when the API key is missing, invalid, or lacks permission.
 */
export class UnauthorizedError extends MaipError {
  constructor(message: string = "Unauthorized: invalid or missing API key") {
    super(message, 401, "UNAUTHORIZED");
    this.name = "UnauthorizedError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Thrown when a requested resource is not found.
 */
export class NotFoundError extends MaipError {
  constructor(resource: string, id: string) {
    super(`${resource} not found: ${id}`, 404, "NOT_FOUND");
    this.name = "NotFoundError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Thrown when bundle or receipt verification fails.
 */
export class VerificationError extends MaipError {
  constructor(message: string) {
    super(message, undefined, "VERIFICATION_FAILED");
    this.name = "VerificationError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}
