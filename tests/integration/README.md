# Integration Tests for Entrypoint

This directory contains integration tests that validate the `entrypoint.py` script against real PostgreSQL, Redis, and Odoo instances running in Docker containers.

## Purpose

While unit tests mock out external dependencies, these integration tests ensure that:

1. The entrypoint script correctly waits for real PostgreSQL and Redis services
2. Generated Odoo commands work with actual database connections
3. Environment variable handling matches production behavior
4. Helper binaries (`odoo-config`, `odoo-update`) are available and functional
5. Version detection works with the real Odoo binary

## Running the Tests

### Automated (CI)

The integration tests run automatically in GitHub Actions for:
- Pull requests to `main`
- Pushes to `main`
- Release builds

### Local Development

To run the integration tests locally:

```bash
cd tests/integration
./run_integration_tests.sh
```

This script will:
1. Build test containers with the current code
2. Start PostgreSQL and Redis services
3. Wait for services to be healthy
4. Run a smoke test (odoo --version)
5. Execute the full integration test suite
6. Clean up all test containers

### Docker Compose Services

The `docker-compose.test.yml` file defines:

- **postgres**: PostgreSQL 15 Alpine with health checks
- **redis**: Redis 7 Alpine with health checks  
- **odoo**: Test container that runs `odoo --version` as a smoke test
- **test-runner**: Container that executes the Python integration tests

### Test Coverage

The integration tests cover:

1. **Service Connectivity**
   - `wait_for_dependencies()` with real PostgreSQL and Redis
   - Database connection with psycopg2
   - Redis connection with redis-py

2. **Command Generation**
   - `build_odoo_command()` produces valid commands
   - All required database parameters are included
   - Environment variables are properly translated to CLI flags

3. **Version Detection**
   - `compute_http_interface()` auto-detection with real Odoo binary
   - Correct interface selection based on version

4. **Helper Binaries**
   - `odoo-config` availability
   - `odoo-update` availability

5. **Environment Handling**
   - PgBouncer precedence over direct PostgreSQL
   - Production behavior (no ENTRYPOINT_DEV_MODE)

## Troubleshooting

If tests fail locally:

1. Check Docker daemon is running
2. Ensure no port conflicts (5432, 6379)
3. View container logs: `docker compose -f docker-compose.test.yml logs`
4. Manually test services:
   ```bash
   docker compose -f docker-compose.test.yml up -d
   docker compose -f docker-compose.test.yml ps
   docker compose -f docker-compose.test.yml down
   ```

## Adding New Tests

To add new integration tests:

1. Add test methods to `test_entrypoint_integration.py`
2. Follow the naming convention `test_<feature>_<scenario>`
3. Use real service connections, not mocks
4. Include proper error messages for debugging
5. Add cleanup in `tearDown` if needed

## Notes

- Integration tests are slower than unit tests due to container startup
- They require Docker to be installed and running
- Tests use health checks to ensure services are ready
- The `ENTRYPOINT_DEV_MODE` is explicitly cleared to test production behavior