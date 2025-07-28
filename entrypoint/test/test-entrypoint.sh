#!/bin/bash
# Test runner for the Python entrypoint script
# This script helps test various entrypoint scenarios without building the full Odoo image

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
TEST_MODE="basic"
CLEANUP=true

# Help function
show_help() {
    cat << EOF
Usage: $0 [OPTIONS] [COMMAND]

Test the Python entrypoint script in various scenarios.

OPTIONS:
    -h, --help          Show this help message
    -n, --no-cleanup    Don't clean up containers after tests
    -m, --mode MODE     Test mode: basic, full, custom, destroy, upgrade
    -c, --compose FILE  Use custom docker-compose file

COMMANDS:
    up                  Start test environment
    down                Stop and clean up test environment
    shell               Start interactive shell for debugging
    test [ARGS]         Run entrypoint with custom arguments
    logs                Show container logs
    reset               Reset test data and containers

EXAMPLES:
    # Basic test
    $0

    # Test with custom command
    $0 test odoo --version

    # Test database initialization
    $0 -m full

    # Interactive debugging
    $0 shell

    # Test destroy functionality
    $0 -m destroy

EOF
}

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
}

# Cleanup function
cleanup() {
    if [ "$CLEANUP" = true ]; then
        log_info "Cleaning up containers..."
        docker-compose -f "$COMPOSE_FILE" down -v
    fi
}

# Ensure cleanup on exit
trap cleanup EXIT

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -n|--no-cleanup)
            CLEANUP=false
            shift
            ;;
        -m|--mode)
            TEST_MODE="$2"
            shift 2
            ;;
        -c|--compose)
            COMPOSE_FILE="$2"
            shift 2
            ;;
        up)
            COMMAND="up"
            shift
            break
            ;;
        down)
            COMMAND="down"
            shift
            break
            ;;
        shell)
            COMMAND="shell"
            shift
            break
            ;;
        test)
            COMMAND="test"
            shift
            TEST_ARGS="$@"
            break
            ;;
        logs)
            COMMAND="logs"
            shift
            break
            ;;
        reset)
            COMMAND="reset"
            shift
            break
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Default command
COMMAND=${COMMAND:-test}

# Create test directories
mkdir -p "$SCRIPT_DIR/test-data" "$SCRIPT_DIR/test-config"

# Execute command
case $COMMAND in
    up)
        log_info "Starting test environment..."
        docker-compose -f "$COMPOSE_FILE" up -d postgres redis
        log_success "Test environment is ready"
        ;;
    
    down)
        log_info "Stopping test environment..."
        docker-compose -f "$COMPOSE_FILE" down -v
        rm -rf "$SCRIPT_DIR/test-data"/* "$SCRIPT_DIR/test-config"/*
        log_success "Test environment stopped and cleaned"
        ;;
    
    shell)
        log_info "Starting interactive shell..."
        docker-compose -f "$COMPOSE_FILE" run --rm debug-shell
        ;;
    
    test)
        log_info "Running entrypoint test..."
        
        # Start services
        docker-compose -f "$COMPOSE_FILE" up -d postgres redis
        
        # Wait for services
        log_info "Waiting for services to be ready..."
        sleep 5
        
        # Run test based on mode
        case $TEST_MODE in
            basic)
                log_info "Running basic test..."
                docker-compose -f "$COMPOSE_FILE" run --rm test-entrypoint \
                    python3 entrypoint/entrypoint.py ${TEST_ARGS:-"--version"}
                ;;
            
            full)
                log_info "Running full initialization test..."
                # Create destroy semaphore to ensure clean start
                touch "$SCRIPT_DIR/test-config/.destroy"
                
                docker-compose -f "$COMPOSE_FILE" run --rm \
                    -e ODOO_LANGUAGES="en_US,en_GB" \
                    -e ODOO_WITHOUT_DEMO="true" \
                    test-entrypoint \
                    python3 entrypoint/entrypoint.py
                ;;
            
            custom)
                log_info "Running custom command test..."
                docker-compose -f "$COMPOSE_FILE" run --rm test-entrypoint \
                    python3 entrypoint/entrypoint.py echo "Custom command works!"
                ;;
            
            destroy)
                log_info "Testing destroy functionality..."
                # Create scaffolded semaphore first
                touch "$SCRIPT_DIR/test-config/.scaffolded"
                # Then create destroy semaphore
                touch "$SCRIPT_DIR/test-config/.destroy"
                
                docker-compose -f "$COMPOSE_FILE" run --rm test-entrypoint \
                    python3 entrypoint/entrypoint.py
                
                # Check if semaphores were removed
                if [ -f "$SCRIPT_DIR/test-config/.scaffolded" ] || [ -f "$SCRIPT_DIR/test-config/.destroy" ]; then
                    log_error "Destroy did not clean up semaphores"
                    exit 1
                fi
                log_success "Destroy functionality works correctly"
                ;;
            
            upgrade)
                log_info "Testing upgrade functionality..."
                # Create scaffolded semaphore
                touch "$SCRIPT_DIR/test-config/.scaffolded"
                # Create old timestamp
                echo "1000000000" > "$SCRIPT_DIR/test-config/.timestamp"
                
                docker-compose -f "$COMPOSE_FILE" run --rm \
                    -e ODOO_ADDONS_TIMESTAMP="2000000000" \
                    test-entrypoint \
                    python3 entrypoint/entrypoint.py
                ;;
            
            *)
                log_error "Unknown test mode: $TEST_MODE"
                exit 1
                ;;
        esac
        
        log_success "Test completed"
        ;;
    
    logs)
        docker-compose -f "$COMPOSE_FILE" logs -f
        ;;
    
    reset)
        log_info "Resetting test environment..."
        docker-compose -f "$COMPOSE_FILE" down -v
        rm -rf "$SCRIPT_DIR/test-data"/* "$SCRIPT_DIR/test-config"/*
        docker-compose -f "$COMPOSE_FILE" up -d postgres redis
        log_success "Test environment reset"
        ;;
    
    *)
        log_error "Unknown command: $COMMAND"
        show_help
        exit 1
        ;;
esac