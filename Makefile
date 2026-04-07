.PHONY: test build lint clean release fmt vet

VERSION ?= $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
LDFLAGS := -s -w -X main.Version=$(VERSION)

# Run all tests
test:
	cd reference && go test -v -race -coverprofile=coverage.out ./...
	cd verifier && go test -v -race ./...

# Build the verifier CLI for the current platform
build:
	cd verifier && go build -ldflags="$(LDFLAGS)" -o ../bin/maip-verifier .

# Run go vet on all packages
vet:
	cd reference && go vet ./...
	cd verifier && go vet ./...

# Run linting (vet + staticcheck if available)
lint: vet
	@which staticcheck > /dev/null 2>&1 && { \
		cd reference && staticcheck ./...; \
		cd ../verifier && staticcheck ./...; \
	} || echo "staticcheck not installed, skipping (install: go install honnef.co/go/tools/cmd/staticcheck@latest)"

# Format all Go files
fmt:
	cd reference && go fmt ./...
	cd verifier && go fmt ./...
	cd examples/register-agent && go fmt ./...
	cd examples/verify-bundle && go fmt ./...

# Build release binaries for all platforms
release: clean
	@mkdir -p bin
	GOOS=linux   GOARCH=amd64 go build -C verifier -ldflags="$(LDFLAGS)" -o ../bin/maip-verifier-linux-amd64 .
	GOOS=linux   GOARCH=arm64 go build -C verifier -ldflags="$(LDFLAGS)" -o ../bin/maip-verifier-linux-arm64 .
	GOOS=darwin  GOARCH=amd64 go build -C verifier -ldflags="$(LDFLAGS)" -o ../bin/maip-verifier-darwin-amd64 .
	GOOS=darwin  GOARCH=arm64 go build -C verifier -ldflags="$(LDFLAGS)" -o ../bin/maip-verifier-darwin-arm64 .
	GOOS=windows GOARCH=amd64 go build -C verifier -ldflags="$(LDFLAGS)" -o ../bin/maip-verifier-windows-amd64.exe .
	GOOS=windows GOARCH=arm64 go build -C verifier -ldflags="$(LDFLAGS)" -o ../bin/maip-verifier-windows-arm64.exe .

# Clean build artifacts
clean:
	rm -rf bin/
	cd reference && rm -f coverage.out
