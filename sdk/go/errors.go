// Copyright 2026 Truthlocks Inc.
// Licensed under the Apache License, Version 2.0

package maip

import "fmt"

// MaipError is the base error type for all MAIP SDK errors.
type MaipError struct {
	Message    string
	StatusCode int
	Code       string
}

func (e *MaipError) Error() string {
	if e.StatusCode > 0 {
		return fmt.Sprintf("maip: %s (HTTP %d, code=%s)", e.Message, e.StatusCode, e.Code)
	}
	return fmt.Sprintf("maip: %s", e.Message)
}

// LimitExceededError is returned when the caller exceeds a rate limit or quota.
type LimitExceededError struct {
	MaipError
	RetryAfterSeconds int
}

// NewLimitExceededError creates a new LimitExceededError.
func NewLimitExceededError(message string, retryAfterSeconds int) *LimitExceededError {
	return &LimitExceededError{
		MaipError: MaipError{
			Message:    message,
			StatusCode: 429,
			Code:       "LIMIT_EXCEEDED",
		},
		RetryAfterSeconds: retryAfterSeconds,
	}
}

// UnauthorizedError is returned when the API key is missing, invalid, or lacks permission.
type UnauthorizedError struct {
	MaipError
}

// NewUnauthorizedError creates a new UnauthorizedError.
func NewUnauthorizedError(message string) *UnauthorizedError {
	if message == "" {
		message = "Unauthorized: invalid or missing API key"
	}
	return &UnauthorizedError{
		MaipError: MaipError{
			Message:    message,
			StatusCode: 401,
			Code:       "UNAUTHORIZED",
		},
	}
}

// NotFoundError is returned when a requested resource is not found.
type NotFoundError struct {
	MaipError
	Resource   string
	Identifier string
}

// NewNotFoundError creates a new NotFoundError.
func NewNotFoundError(resource, identifier string) *NotFoundError {
	return &NotFoundError{
		MaipError: MaipError{
			Message:    fmt.Sprintf("%s not found: %s", resource, identifier),
			StatusCode: 404,
			Code:       "NOT_FOUND",
		},
		Resource:   resource,
		Identifier: identifier,
	}
}

// VerificationError is returned when bundle or receipt verification fails.
type VerificationError struct {
	MaipError
}

// NewVerificationError creates a new VerificationError.
func NewVerificationError(message string) *VerificationError {
	return &VerificationError{
		MaipError: MaipError{
			Message: message,
			Code:    "VERIFICATION_FAILED",
		},
	}
}
