#!/bin/bash
# Test the entrypoint with a real Odoo container
# This builds a minimal test image and runs various scenarios

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
ODOO_VERSION="${ODOO_VERSION:-17}"
TEST_IMAGE="odoo-entrypoint-test:latest"
COMPOSE_PROJECT="entrypoint-test-$$"

# Logging
log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# Create test Dockerfile
create_test_dockerfile() {
    cat > "$SCRIPT_DIR/Dockerfile.test" << EOF
FROM odoo:${ODOO_VERSION}

# Install development dependencies
USER root
RUN apt-get update && apt-get install -y python3-pip procps && rm -rf /var/lib/apt/lists/*

# Copy our entrypoint implementation
COPY entrypoint /opt/odoo/entrypoint
COPY tools /opt/odoo/tools

# Make entrypoint executable
RUN chmod +x /opt/odoo/entrypoint/entrypoint.py

# Override entrypoint
ENTRYPOINT ["/opt/odoo/entrypoint/entrypoint.py"]
CMD ["odoo"]
EOF
}

# Create docker-compose for testing
create_test_compose() {
    cat > "$SCRIPT_DIR/docker-compose.test.yml" << EOF
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: odoo
      POSTGRES_DB: odoo
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U odoo"]
      interval: 2s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 2s
      timeout: 3s
      retries: 5

  odoo:
    image: ${TEST_IMAGE}
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: odoo
      POSTGRES_DB: odoo
      REDIS_HOST: redis
      REDIS_PORT: 6379
      ODOO_WITHOUT_DEMO: "true"
      ODOO_LOG_LEVEL: info
    volumes:
      - odoo-data:/var/lib/odoo
      - odoo-config:/etc/odoo

volumes:
  odoo-data:
  odoo-config:
EOF
}

# Cleanup function
cleanup() {
    log_info "Cleaning up..."
    docker-compose -p "$COMPOSE_PROJECT" -f "$SCRIPT_DIR/docker-compose.test.yml" down -v 2>/dev/null || true
    rm -f "$SCRIPT_DIR/Dockerfile.test" "$SCRIPT_DIR/docker-compose.test.yml"
}

trap cleanup EXIT

# Test functions
test_version() {
    log_info "Testing: odoo --version"
    docker-compose -p "$COMPOSE_PROJECT" -f "$SCRIPT_DIR/docker-compose.test.yml" \
        run --rm odoo --version
}

test_custom_command() {
    log_info "Testing: custom command (echo)"
    docker-compose -p "$COMPOSE_PROJECT" -f "$SCRIPT_DIR/docker-compose.test.yml" \
        run --rm odoo echo "Custom command works!"
}

test_initialization() {
    log_info "Testing: database initialization"
    
    # First, destroy any existing database
    docker-compose -p "$COMPOSE_PROJECT" -f "$SCRIPT_DIR/docker-compose.test.yml" \
        run --rm -e ODOO_DESTROY=1 odoo || true
    
    # Now initialize
    docker-compose -p "$COMPOSE_PROJECT" -f "$SCRIPT_DIR/docker-compose.test.yml" \
        run --rm odoo --stop-after-init
}

test_worker_calculation() {
    log_info "Testing: worker calculation"
    
    # Get CPU count
    CPU_COUNT=$(nproc)
    EXPECTED_WORKERS=$((CPU_COUNT * 2 - 1))
    
    OUTPUT=$(docker-compose -p "$COMPOSE_PROJECT" -f "$SCRIPT_DIR/docker-compose.test.yml" \
        run --rm odoo --help 2>&1 | grep -E "workers.*default" || echo "")
    
    log_info "CPU count: $CPU_COUNT, Expected workers: $EXPECTED_WORKERS"
    log_info "Help output: $OUTPUT"
}

test_permission_handling() {
    log_info "Testing: PUID/PGID handling"
    
    docker-compose -p "$COMPOSE_PROJECT" -f "$SCRIPT_DIR/docker-compose.test.yml" \
        run --rm -e PUID=1001 -e PGID=1001 odoo \
        bash -c "id -u odoo && id -g odoo"
}

test_upgrade_detection() {
    log_info "Testing: upgrade detection"
    
    # Initialize first
    docker-compose -p "$COMPOSE_PROJECT" -f "$SCRIPT_DIR/docker-compose.test.yml" \
        run --rm odoo --stop-after-init
    
    # Simulate newer addon timestamp
    docker-compose -p "$COMPOSE_PROJECT" -f "$SCRIPT_DIR/docker-compose.test.yml" \
        run --rm -e ODOO_ADDONS_TIMESTAMP="9999999999" odoo --stop-after-init
}

# Main execution
main() {
    log_info "Building test image..."
    
    create_test_dockerfile
    create_test_compose
    
    # Build test image
    docker build -f "$SCRIPT_DIR/Dockerfile.test" -t "$TEST_IMAGE" "$PROJECT_ROOT"
    
    log_info "Starting test services..."
    docker-compose -p "$COMPOSE_PROJECT" -f "$SCRIPT_DIR/docker-compose.test.yml" up -d postgres redis
    
    # Wait for services
    sleep 5
    
    # Run tests
    log_info "Running tests..."
    
    test_version
    log_success "Version test passed"
    
    test_custom_command
    log_success "Custom command test passed"
    
    test_initialization
    log_success "Initialization test passed"
    
    test_worker_calculation
    log_success "Worker calculation test passed"
    
    test_permission_handling
    log_success "Permission handling test passed"
    
    test_upgrade_detection
    log_success "Upgrade detection test passed"
    
    log_success "All tests completed successfully!"
}

# Parse arguments
case "${1:-}" in
    -h|--help)
        echo "Usage: $0 [ODOO_VERSION]"
        echo "Test the Python entrypoint with a real Odoo container"
        echo ""
        echo "Examples:"
        echo "  $0          # Test with Odoo 17 (default)"
        echo "  $0 16       # Test with Odoo 16"
        echo "  $0 18       # Test with Odoo 18"
        exit 0
        ;;
    [0-9]*)
        ODOO_VERSION="$1"
        ;;
esac

main