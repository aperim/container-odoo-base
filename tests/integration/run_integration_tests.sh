#!/bin/bash
# Integration test runner for entrypoint.py
# This script sets up real PostgreSQL, Redis, and Odoo containers to test
# the entrypoint script in a production-like environment.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

echo "=== Entrypoint Integration Tests ==="
echo "Running integration tests with real PostgreSQL, Redis, and Odoo..."
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Cleanup function
cleanup() {
    echo
    echo "Cleaning up test containers..."
    cd "${SCRIPT_DIR}"
    docker compose -f docker-compose.test.yml down -v --remove-orphans || true
}

# Set up cleanup on exit
trap cleanup EXIT INT TERM

# Change to integration test directory
cd "${SCRIPT_DIR}"

# Build the test environment
echo "Building test containers..."
docker compose -f docker-compose.test.yml build

# Start services
echo "Starting PostgreSQL and Redis services..."
docker compose -f docker-compose.test.yml up -d postgres redis

# Wait for services to be healthy
echo "Waiting for services to be healthy..."
timeout=60
elapsed=0
while [ $elapsed -lt $timeout ]; do
    if docker compose -f docker-compose.test.yml ps | grep -E "(postgres|redis).*healthy" | wc -l | grep -q "2"; then
        echo -e "${GREEN}Services are healthy!${NC}"
        break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
    echo "Waiting... ($elapsed/$timeout seconds)"
done

if [ $elapsed -ge $timeout ]; then
    echo -e "${RED}Timeout waiting for services to be healthy${NC}"
    docker compose -f docker-compose.test.yml ps
    exit 1
fi

# Run the version test first (simple smoke test)
echo
echo "Running Odoo version test..."
if docker compose -f docker-compose.test.yml run --rm odoo; then
    echo -e "${GREEN}✓ Odoo version test passed${NC}"
else
    echo -e "${RED}✗ Odoo version test failed${NC}"
    exit 1
fi

# Run the integration tests
echo
echo "Running integration test suite..."
if docker compose -f docker-compose.test.yml run --rm test-runner; then
    echo -e "${GREEN}✓ All integration tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Integration tests failed${NC}"
    exit 1
fi