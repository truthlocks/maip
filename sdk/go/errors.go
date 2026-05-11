package truthlock

import "fmt"

// ErrorCode represents stable error codes returned by the API.
type ErrorCode string

const (
	ErrInvalidInput     ErrorCode = "INVALID_INPUT"
	ErrNotFound         ErrorCode = "NOT_FOUND"
	ErrUnauthorized     ErrorCode = "UNAUTHORIZED"
	ErrForbidden        ErrorCode = "FORBIDDEN"
	ErrConflict         ErrorCode = "CONFLICT"
	ErrInternalError    ErrorCode = "INTERNAL_ERROR"
	ErrIssuerNotTrusted ErrorCode = "ISSUER_NOT_TRUSTED"
	ErrIssuerSuspended  ErrorCode = "ISSUER_SUSPENDED"
	ErrIssuerRevoked    ErrorCode = "ISSUER_REVOKED"
	ErrKeyNotFound      ErrorCode = "KEY_NOT_FOUND"
	ErrKeyInactive      ErrorCode = "KEY_INACTIVE"
	ErrKeyExpired       ErrorCode = "KEY_EXPIRED"
	ErrKeyCompromised   ErrorCode = "KEY_COMPROMISED"
	ErrPolicyViolation  ErrorCode = "POLICY_VIOLATION"
)

// TruthlockError represents an error from the Truthlock API.
type TruthlockError struct {
	// Code is the stable error code for programmatic handling.
	Code ErrorCode `json:"code"`
	// Message is a human-readable error message.
	Message string `json:"message"`
	// Status is the HTTP status code.
	Status int `json:"status"`
	// TraceID is for debugging and support.
	TraceID string `json:"trace_id,omitempty"`
	// Details contains additional error context.
	Details map[string]interface{} `json:"details,omitempty"`
}

// Error implements the error interface.
func (e *TruthlockError) Error() string {
	return fmt.Sprintf("[%s] %s (status=%d)", e.Code, e.Message, e.Status)
}

// Unwrap returns nil since TruthlockError is the root error type.
func (e *TruthlockError) Unwrap() error {
	return nil
}

// IsCode checks if the error has the given code.
func (e *TruthlockError) IsCode(code ErrorCode) bool {
	return e.Code == code
}

// NotFoundError returns true if this is a not found error.
func (e *TruthlockError) NotFoundError() bool {
	return e.Code == ErrNotFound || e.Status == 404
}

// AuthorizationError returns true if this is an auth error.
func (e *TruthlockError) AuthorizationError() bool {
	return e.Code == ErrUnauthorized || e.Code == ErrForbidden
}

// ValidationError returns true if this is a validation error.
func (e *TruthlockError) ValidationError() bool {
	return e.Code == ErrInvalidInput || e.Status == 400
}
