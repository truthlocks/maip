// Copyright 2026 Truthlocks Inc.
// Licensed under the Apache License, Version 2.0

// Package maip provides a Go SDK for the Machine Agent Identity Protocol (MAIP).
//
// It supports both the hosted Truthlocks API (https://api.truthlocks.com) and
// self-hosted deployments.
//
// Example:
//
//	client := maip.NewClient("your-api-key")
//	agent, err := client.RegisterAgent(ctx, maip.CreateAgentRequest{
//	    Name:      "my-agent",
//	    Scope:     maip.Scope{Actions: []string{"read"}, Resources: []string{"*"}},
//	    PublicKey: "base64-encoded-public-key",
//	})
package maip

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const (
	defaultBaseURL = "https://api.truthlocks.com"
	defaultTimeout = 30 * time.Second
	userAgent      = "truthlocks-maip-go/0.1.0"
)

// ClientOption configures the Client.
type ClientOption func(*Client)

// WithBaseURL sets a custom base URL (for self-hosted deployments).
func WithBaseURL(baseURL string) ClientOption {
	return func(c *Client) {
		c.baseURL = strings.TrimRight(baseURL, "/")
	}
}

// WithTimeout sets the HTTP request timeout.
func WithTimeout(timeout time.Duration) ClientOption {
	return func(c *Client) {
		c.httpClient.Timeout = timeout
	}
}

// WithHTTPClient sets a custom HTTP client.
func WithHTTPClient(httpClient *http.Client) ClientOption {
	return func(c *Client) {
		c.httpClient = httpClient
	}
}

// Client is the MAIP SDK client.
type Client struct {
	apiKey     string
	baseURL    string
	httpClient *http.Client
}

// NewClient creates a new MAIP SDK client.
func NewClient(apiKey string, opts ...ClientOption) *Client {
	c := &Client{
		apiKey:  apiKey,
		baseURL: defaultBaseURL,
		httpClient: &http.Client{
			Timeout: defaultTimeout,
		},
	}
	for _, opt := range opts {
		opt(c)
	}
	return c
}

// ---------------------------------------------------------------------------
// Agent Management
// ---------------------------------------------------------------------------

// RegisterAgent registers a new agent identity.
func (c *Client) RegisterAgent(ctx context.Context, req CreateAgentRequest) (*Agent, error) {
	var agent Agent
	if err := c.post(ctx, "/v1/agents", req, &agent); err != nil {
		return nil, err
	}
	return &agent, nil
}

// ListAgents lists agents with optional filters.
func (c *Client) ListAgents(ctx context.Context, opts *ListAgentsOptions) (*ListResponse[Agent], error) {
	params := url.Values{}
	if opts != nil {
		if opts.Status != nil {
			params.Set("status", string(*opts.Status))
		}
		if opts.Offset != nil {
			params.Set("offset", strconv.Itoa(*opts.Offset))
		}
		if opts.Limit != nil {
			params.Set("limit", strconv.Itoa(*opts.Limit))
		}
	}
	var resp ListResponse[Agent]
	if err := c.get(ctx, "/v1/agents", params, &resp); err != nil {
		return nil, err
	}
	return &resp, nil
}

// GetAgent retrieves a single agent by ID.
func (c *Client) GetAgent(ctx context.Context, agentID string) (*Agent, error) {
	var agent Agent
	if err := c.get(ctx, fmt.Sprintf("/v1/agents/%s", url.PathEscape(agentID)), nil, &agent); err != nil {
		return nil, err
	}
	return &agent, nil
}

// SuspendAgent suspends an active agent.
func (c *Client) SuspendAgent(ctx context.Context, agentID string) (*Agent, error) {
	var agent Agent
	if err := c.post(ctx, fmt.Sprintf("/v1/agents/%s/suspend", url.PathEscape(agentID)), struct{}{}, &agent); err != nil {
		return nil, err
	}
	return &agent, nil
}

// RevokeAgent permanently revokes an agent identity.
func (c *Client) RevokeAgent(ctx context.Context, agentID string) (*Agent, error) {
	var agent Agent
	if err := c.post(ctx, fmt.Sprintf("/v1/agents/%s/revoke", url.PathEscape(agentID)), struct{}{}, &agent); err != nil {
		return nil, err
	}
	return &agent, nil
}

// ---------------------------------------------------------------------------
// Session Management
// ---------------------------------------------------------------------------

// CreateSession creates a new authenticated session for an agent.
func (c *Client) CreateSession(ctx context.Context, req CreateSessionRequest) (*Session, error) {
	var session Session
	if err := c.post(ctx, "/v1/sessions", req, &session); err != nil {
		return nil, err
	}
	return &session, nil
}

// TerminateSession terminates an active session.
func (c *Client) TerminateSession(ctx context.Context, sessionID string) (*Session, error) {
	var session Session
	if err := c.post(ctx, fmt.Sprintf("/v1/sessions/%s/terminate", url.PathEscape(sessionID)), struct{}{}, &session); err != nil {
		return nil, err
	}
	return &session, nil
}

// ---------------------------------------------------------------------------
// Trust
// ---------------------------------------------------------------------------

// GetTrustScore gets the current trust score for an agent.
func (c *Client) GetTrustScore(ctx context.Context, agentID string) (*TrustScore, error) {
	var score TrustScore
	if err := c.get(ctx, fmt.Sprintf("/v1/agents/%s/trust-score", url.PathEscape(agentID)), nil, &score); err != nil {
		return nil, err
	}
	return &score, nil
}

// ComputeTrustScore computes a fresh trust score for an agent.
func (c *Client) ComputeTrustScore(ctx context.Context, req ComputeTrustScoreRequest) (*TrustScore, error) {
	var score TrustScore
	if err := c.post(ctx, fmt.Sprintf("/v1/agents/%s/trust-score/compute", url.PathEscape(req.AgentID)), req, &score); err != nil {
		return nil, err
	}
	return &score, nil
}

// ---------------------------------------------------------------------------
// Delegation
// ---------------------------------------------------------------------------

// OfferDelegation offers a trust delegation from one agent to another.
func (c *Client) OfferDelegation(ctx context.Context, req OfferDelegationRequest) (*Delegation, error) {
	var delegation Delegation
	if err := c.post(ctx, "/v1/delegations", req, &delegation); err != nil {
		return nil, err
	}
	return &delegation, nil
}

// AcceptDelegation accepts an offered delegation.
func (c *Client) AcceptDelegation(ctx context.Context, delegationID string) (*Delegation, error) {
	var delegation Delegation
	if err := c.post(ctx, fmt.Sprintf("/v1/delegations/%s/accept", url.PathEscape(delegationID)), struct{}{}, &delegation); err != nil {
		return nil, err
	}
	return &delegation, nil
}

// ---------------------------------------------------------------------------
// Orchestration
// ---------------------------------------------------------------------------

// ExecuteOrchestration executes a multi-agent orchestration.
func (c *Client) ExecuteOrchestration(ctx context.Context, req ExecuteOrchestrationRequest) (*Orchestration, error) {
	var orchestration Orchestration
	if err := c.post(ctx, "/v1/orchestrations", req, &orchestration); err != nil {
		return nil, err
	}
	return &orchestration, nil
}

// ---------------------------------------------------------------------------
// Guardrails
// ---------------------------------------------------------------------------

// CheckGuardrails checks guardrails before performing an action.
func (c *Client) CheckGuardrails(ctx context.Context, req CheckGuardrailsRequest) (*GuardrailResult, error) {
	var result GuardrailResult
	if err := c.post(ctx, "/v1/guardrails/check", req, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

func (c *Client) get(ctx context.Context, path string, params url.Values, out any) error {
	u := c.baseURL + path
	if len(params) > 0 {
		u += "?" + params.Encode()
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return &MaipError{Message: fmt.Sprintf("failed to create request: %v", err)}
	}

	return c.do(req, out)
}

func (c *Client) post(ctx context.Context, path string, body any, out any) error {
	data, err := json.Marshal(body)
	if err != nil {
		return &MaipError{Message: fmt.Sprintf("failed to marshal request body: %v", err)}
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, bytes.NewReader(data))
	if err != nil {
		return &MaipError{Message: fmt.Sprintf("failed to create request: %v", err)}
	}

	return c.do(req, out)
}

func (c *Client) do(req *http.Request, out any) error {
	req.Header.Set("Authorization", "Bearer "+c.apiKey)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", userAgent)

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return &MaipError{Message: fmt.Sprintf("request failed: %v", err)}
	}
	defer resp.Body.Close()

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return &MaipError{Message: fmt.Sprintf("failed to read response: %v", err)}
	}

	if resp.StatusCode >= 400 {
		return c.handleErrorResponse(resp, respBody)
	}

	if out != nil && len(respBody) > 0 {
		if err := json.Unmarshal(respBody, out); err != nil {
			return &MaipError{Message: fmt.Sprintf("failed to decode response: %v", err)}
		}
	}

	return nil
}

func (c *Client) handleErrorResponse(resp *http.Response, body []byte) error {
	var errBody struct {
		Message string `json:"message"`
		Code    string `json:"code"`
	}
	_ = json.Unmarshal(body, &errBody)

	message := errBody.Message
	if message == "" {
		message = fmt.Sprintf("HTTP %d", resp.StatusCode)
	}

	switch resp.StatusCode {
	case 401:
		return NewUnauthorizedError(message)
	case 404:
		return NewNotFoundError("Resource", message)
	case 429:
		retryAfter := 0
		if s := resp.Header.Get("Retry-After"); s != "" {
			retryAfter, _ = strconv.Atoi(s)
		}
		return NewLimitExceededError(message, retryAfter)
	default:
		return &MaipError{
			Message:    message,
			StatusCode: resp.StatusCode,
			Code:       errBody.Code,
		}
	}
}
