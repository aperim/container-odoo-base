# Odoo Enterprise Docker Container

An Odoo Enterprise Docker container with advanced initialization scripts and configuration management.

## Table of Contents

- [Introduction](#introduction)
- [Features](#features)
- [Requirements](#requirements)
- [Environment Variables](#environment-variables)
- [Building the Containers](#building-the-containers)
- [Running the Containers](#running-the-containers)
- [Docker Compose Examples](#docker-compose-examples)
  - [Docker Compose for Docker Swarm](#docker-compose-for-docker-swarm)
- [Additional Scripts and Tools](#additional-scripts-and-tools)
- [Directory Structure](#directory-structure)
- [Contributing](#contributing)
- [License](#license)

## Introduction

This repository provides a Docker-based deployment of Odoo Enterprise, including custom initialization scripts, configuration management, and support for Docker Swarm deployments. The setup includes:

- Odoo Community and Enterprise code, pulled from specified repositories.
- Custom entrypoint scripts to handle database initialization, addon management, and more.
- Nginx reverse proxy container for serving the Odoo application.

## Features

- **Automated Odoo Initialization**: Entry scripts handle the initialization of the Odoo database, addons, and configurations.
- **Addon Management**: Automatic discovery and installation of Odoo addons from community, enterprise, and custom sources.
- **Customisable Environment**: Control your deployment via environment variables.
- **Redis and PostgreSQL Integration**: Supports waiting for and connecting to Redis and PostgreSQL services.
- **Docker Swarm Support**: Includes examples and scripts for deploying on Docker Swarm with Docker Compose.

## Requirements

- Docker Engine version 20.10 or higher.
- Docker Compose or Docker Swarm (depending on your deployment preference).
- Access to Odoo Enterprise repositories (requires valid subscription and credentials).
- GitHub Personal Access Token with permissions to clone private repositories (for Odoo Enterprise).

## Environment Variables

The containers rely on several environment variables to customise their behaviour. These variables may be required or optional depending on your configuration.

### Odoo Configuration

- `ODOO_MAJOR_VERSION` (required): The major version of Odoo to deploy (e.g., `17`).
- `ODOO_MINOR_VERSION` (optional): The minor version of Odoo (e.g., `0`). Defaults to `0`.
- `ODOO_MASTER_PASSWORD` (required): The master password for the Odoo database.
- `ODOO_LANGUAGES` (optional): A comma-separated list of language codes to install (e.g., `en_AU,en_US`). Defaults to `en_AU,en_US`.

### GitHub Credentials

- `GITHUB_TOKEN` (required): GitHub Personal Access Token with permissions to clone private repositories (e.g., Odoo Enterprise).
- `GITHUB_USER` (required): GitHub username associated with the token.
- `GITHUB_EMAIL` (optional): GitHub email address associated with your GitHub account.

### Odoo Repositories

- `ODOO_COMMUNITY_REPOSITORY` (optional): URL of the Odoo Community repository. Defaults to `github.com/odoo/odoo`.
- `ODOO_ENTERPRISE_REPOSITORY` (required): URL of the Odoo Enterprise repository (e.g., `github.com/odoo/enterprise`).

### Database Configuration

- `POSTGRES_HOST` (required): Hostname of the PostgreSQL server.
- `POSTGRES_PORT` (optional): Port number of the PostgreSQL server. Defaults to `5432`.
- `POSTGRES_USER` (required): PostgreSQL username.
- `POSTGRES_PASSWORD` (required): PostgreSQL password.
- `POSTGRES_DB` (required): Name of the Odoo database.
- `POSTGRES_SSL_MODE` (optional): SSL mode for PostgreSQL connection. Can be `disable`, `require`, `verify-ca`, or `verify-full`. Defaults to `disable`.

### Redis Configuration

- `REDIS_HOST` (required): Hostname of the Redis server.
- `REDIS_PORT` (optional): Port number of the Redis server. Defaults to `6379`.
- `REDIS_PASSWORD` (optional): Password for the Redis server.
- `REDIS_SSL` (optional): Set to `true` to enable SSL/TLS for Redis connections. Defaults to `false`.
- `REDIS_SSL_CA_CERTS` (optional): Path to CA certificates file if using SSL/TLS.
- `REDIS_SSL_CERTFILE` (optional): Path to client certificate file if using SSL/TLS.
- `REDIS_SSL_KEYFILE` (optional): Path to client key file if using SSL/TLS.
- `REDIS_SSL_CHECK_HOSTNAME` (optional): `true` or `false` to enable/disable hostname verification. Defaults to `false`.
- `REDIS_SSL_CERT_REQS` (optional): `none`, `optional`, or `required`. Defaults to `required`.

### Other Configurations

- `PGBOUNCER_HOST` (optional): Hostname of the PgBouncer service if used.
- `PGBOUNCER_PORT` (optional): Port of the PgBouncer service. Defaults to `5432`.
- `PGBOUNCER_SSL_MODE` (optional): SSL mode for PgBouncer connection.

### GeoIP Configuration

- `GEOIPUPDATE_ACCOUNT_ID` (optional): Account ID for GeoIP updates.
- `GEOIPUPDATE_LICENSE_KEY` (optional): License key for GeoIP updates.

### User and Group Configuration

- `PUID` (optional): The user ID that the Odoo container should run as.
- `PGID` (optional): The group ID that the Odoo container should run as.

## Building the Containers

The repository includes Dockerfiles for both the Odoo application and the Nginx reverse proxy.

### Build Odoo Docker Image

```bash
docker build -t odoo -f Dockerfile.odoo .
```

### Build Nginx Docker Image

```bash
docker build -t odoo-nginx -f Dockerfile.nginx .
```

## Running the Containers

You can run the containers individually or orchestrate them using Docker Compose. Make sure to pass all required environment variables.

### Running Odoo Container

```bash
docker run -d --name odoo \
  -p 8069:8069 \
  -e ODOO_MASTER_PASSWORD=your_master_password \
  -e POSTGRES_HOST=your_postgres_host \
  -e POSTGRES_USER=your_postgres_user \
  -e POSTGRES_PASSWORD=your_postgres_password \
  -e POSTGRES_DB=your_database_name \
  -e POSTGRES_SSL_MODE=disable \
  -e REDIS_HOST=your_redis_host \
  -e REDIS_PASSWORD=your_redis_password \
  -e GITHUB_TOKEN=your_github_token \
  -e ODOO_MAJOR_VERSION=17 \
  -e ODOO_MINOR_VERSION=0 \
  -v odoo-data:/var/lib/odoo \
  -v odoo-config:/etc/odoo \
  ghcr.io/yourusername/odoo:17.0e
```

**Note**: Replace `yourusername` with your GitHub username or organisation.

### Running Nginx Container

```bash
docker run -d --name odoo-nginx \
  -p 80:80 \
  -e ODOO_HOST=odoo \
  -e ODOO_PORT=8069 \
  -e ODOO_TLS=false \
  --link odoo:odoo \
  ghcr.io/yourusername/odoo-nginx:17.0e
```

## Docker Compose Examples

Below are examples of `docker-compose.yml` configurations for deploying the Odoo and Nginx containers, including supporting services like PostgreSQL and Redis.

### Docker Compose for Docker Swarm

Create a `docker-compose.yml` file with the following content:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:13
    environment:
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: odoo
      POSTGRES_DB: odoo
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks:
      - odoo-network
    deploy:
      placement:
        constraints:
          - node.role == manager

  redis:
    image: redis:6
    command: ["redis-server", "--requirepass", "your_redis_password"]
    environment:
      REDIS_PASSWORD: your_redis_password
    networks:
      - odoo-network

  odoo:
    image: ghcr.io/yourusername/odoo:17.0e
    depends_on:
      - postgres
      - redis
    environment:
      ODOO_MASTER_PASSWORD: your_master_password
      POSTGRES_HOST: postgres
      POSTGRES_PORT: 5432
      POSTGRES_USER: odoo
      POSTGRES_PASSWORD: odoo
      POSTGRES_DB: odoo
      POSTGRES_SSL_MODE: disable
      REDIS_HOST: redis
      REDIS_PORT: 6379
      REDIS_PASSWORD: your_redis_password
      REDIS_SSL: "false"
      GITHUB_TOKEN: your_github_token
      ODOO_MAJOR_VERSION: "17"
      ODOO_MINOR_VERSION: "0"
      ODOO_LANGUAGES: "en_AU,en_US"
    volumes:
      - odoo-data:/var/lib/odoo
      - odoo-config:/etc/odoo
    networks:
      - odoo-network
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure

  nginx:
    image: ghcr.io/yourusername/odoo-nginx:17.0e
    ports:
      - "80:80"
    depends_on:
      - odoo
    environment:
      ODOO_HOST: odoo
      ODOO_PORT: 8069
      ODOO_TLS: "false"
    networks:
      - odoo-network
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure

networks:
  odoo-network:
    driver: overlay

volumes:
  pgdata:
  odoo-data:
  odoo-config:
```

### Deploying to Docker Swarm

Initialise Docker Swarm if not already done:

```bash
docker swarm init
```

Deploy the stack:

```bash
docker stack deploy -c docker-compose.yml odoo-stack
```

### Scaling Services

You can scale the Odoo service to have multiple replicas:

```bash
docker service scale odoo-stack_odoo=3
```

**Note**: Ensure that your configuration supports multiple Odoo instances (e.g., shared database, load balancing, session management).

## Additional Scripts and Tools

The containers include several custom scripts and tools:

- **`entrypoint.sh`**: The entrypoint script for the Odoo container, handling initialization tasks.
- **`odoo-config`**: A script for managing the `odoo.conf` configuration file.
- **`odoo-addon-updater`**: Ensures that shipped Odoo addons are present and up-to-date.
- **`wait-for-postgres`**: Waits for PostgreSQL and PgBouncer services to become available.
- **`wait-for-initialization`**: Waits for the Odoo instance to be initialized by another replica.
- **`lock-handler`**: Handles Redis-based locking with TLS support.

## Directory Structure

- **`Dockerfile.odoo`**: Dockerfile for building the Odoo application container.
- **`Dockerfile.nginx`**: Dockerfile for building the Nginx reverse proxy container.
- **`entrypoint/entrypoint.sh`**: Entrypoint script for the Odoo container.
- **`tools/src/`**: Contains utility scripts used by the containers.
- **`extras/`**: Extra addons and custom modules for Odoo.
- **`builder/src/`**: Scripts for building and preparing the Odoo image.
- **`nginx/`**: Configuration and scripts for the Nginx container.
- **`.env.example`**: Example environment variable definitions.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Environment

To set up a development environment:

1. Clone the repository.
2. Copy `.env.example` to `.env` and fill in the required variables.
3. Build the containers using the provided Dockerfiles.
4. Use the `docker-compose.yml` file for local testing.

## License

This project is commercially protected.
