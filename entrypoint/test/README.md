# Entrypoint Testing Framework

This directory contains tools for testing the Python entrypoint script locally without waiting for CI/CD pipelines or building full Docker images.

## Quick Start

```bash
# Basic test - runs entrypoint with --version
./test-entrypoint.sh

# Test with real Odoo container
./test-with-odoo.sh

# Interactive debugging
./test-entrypoint.sh shell
```

## Available Test Scripts

### 1. `test-entrypoint.sh` - Lightweight Testing

Tests the entrypoint script using minimal Python containers with mock services.

**Features:**
- Fast startup (uses python:3.11-slim)
- No Odoo installation required
- Perfect for testing entrypoint logic
- Interactive debugging mode

**Usage:**
```bash
# Basic test
./test-entrypoint.sh

# Test specific functionality
./test-entrypoint.sh -m full        # Full initialization
./test-entrypoint.sh -m destroy     # Test destroy functionality
./test-entrypoint.sh -m upgrade     # Test upgrade detection
./test-entrypoint.sh -m custom      # Test custom commands

# Custom arguments
./test-entrypoint.sh test --help
./test-entrypoint.sh test odoo --version

# Interactive shell for debugging
./test-entrypoint.sh shell

# View logs
./test-entrypoint.sh logs

# Reset environment
./test-entrypoint.sh reset
```

### 2. `test-with-odoo.sh` - Full Integration Testing

Tests the entrypoint with a real Odoo container, ensuring compatibility with the actual runtime environment.

**Features:**
- Builds test image with your entrypoint
- Tests with real Odoo binaries
- Validates all integration points
- Tests multiple Odoo versions

**Usage:**
```bash
# Test with default Odoo version (17)
./test-with-odoo.sh

# Test with specific version
./test-with-odoo.sh 16
./test-with-odoo.sh 18

# The script automatically runs:
# - Version check
# - Custom command passthrough
# - Database initialization
# - Worker calculation
# - Permission handling (PUID/PGID)
# - Upgrade detection
```

### 3. `docker-compose.yml` - Manual Testing

Provides a complete test environment for manual testing and debugging.

**Services:**
- `postgres`: PostgreSQL database
- `redis`: Redis for locking
- `test-entrypoint`: Python container for testing
- `debug-shell`: Interactive shell container

**Usage:**
```bash
# Start services
docker-compose -f docker-compose.yml up -d

# Run tests manually
docker-compose -f docker-compose.yml run --rm test-entrypoint \
    python3 entrypoint/entrypoint.py --version

# Interactive debugging
docker-compose -f docker-compose.yml run --rm debug-shell

# Clean up
docker-compose -f docker-compose.yml down -v
```

## Test Scenarios

### 1. Basic Functionality
- Command-line parsing
- Environment variable handling
- Custom command detection
- Version output

### 2. Service Dependencies
- Redis connectivity
- PostgreSQL connectivity
- PgBouncer support
- Connection retry logic

### 3. Database Operations
- Database destruction
- Fresh initialization
- Restore from backup
- Module installation

### 4. Runtime Configuration
- User/group ID mutation (PUID/PGID)
- File permissions
- Configuration file updates
- Worker count calculation

### 5. Upgrade Management
- Timestamp comparison
- Module upgrade logic
- Retry mechanisms
- Lock handling

## Development Workflow

1. **Make changes** to `entrypoint/entrypoint.py`

2. **Run quick tests** to verify basic functionality:
   ```bash
   ./test-entrypoint.sh
   ```

3. **Test specific scenarios** as needed:
   ```bash
   ./test-entrypoint.sh -m destroy
   ./test-entrypoint.sh -m upgrade
   ```

4. **Debug issues** interactively:
   ```bash
   ./test-entrypoint.sh shell
   # Inside container:
   python3 entrypoint/entrypoint.py --help
   ```

5. **Run full integration tests** before committing:
   ```bash
   ./test-with-odoo.sh
   ```

## Environment Variables

The test scripts support all standard entrypoint environment variables:

```bash
# Database configuration
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_USER=odoo
POSTGRES_PASSWORD=odoo
POSTGRES_DB=odoo

# Redis configuration
REDIS_HOST=redis
REDIS_PORT=6379

# Odoo configuration
ODOO_WITHOUT_DEMO=true
ODOO_LOG_LEVEL=debug
ODOO_LANGUAGES=en_US,en_GB

# Runtime user
PUID=1000
PGID=1000

# Development mode (bypasses some checks)
ENTRYPOINT_DEV_MODE=1
```

## Troubleshooting

### Services won't start
```bash
# Check if ports are in use
docker ps
lsof -i :15432  # PostgreSQL
lsof -i :16379  # Redis

# Reset everything
./test-entrypoint.sh reset
```

### Permission errors
```bash
# The test scripts create local directories that may have wrong permissions
sudo rm -rf test-data test-config
./test-entrypoint.sh reset
```

### Can't connect to services
```bash
# Ensure services are healthy
docker-compose -f docker-compose.yml ps
docker-compose -f docker-compose.yml logs postgres
docker-compose -f docker-compose.yml logs redis
```

### Tests hang
```bash
# The entrypoint may be waiting for services
# Check if ENTRYPOINT_DEV_MODE=1 is set for lightweight tests
# Kill hanging containers
docker ps -q | xargs docker kill
```

## CI/CD Integration

These test scripts can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Test entrypoint
  run: |
    cd entrypoint/test
    ./test-entrypoint.sh -m full
    ./test-with-odoo.sh
```

## Contributing

When adding new functionality to the entrypoint:

1. Add corresponding test cases to the test scripts
2. Document any new environment variables
3. Update this README if needed
4. Ensure all tests pass before submitting PR