# Odoo Container Generator

Welcome to the **Odoo Container Generator** repository. This project centralises the work required to generate working Odoo Community and Enterprise Docker containers. Due to licensing requirements, the generated containers are **not publicly available** and cannot be shared. However, you can fork this repository and set it up to generate your own containers.

## Table of Contents

- [Overview](#overview)
- [Disclaimer](#disclaimer)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Forking the Repository](#forking-the-repository)
  - [Setting Up Your Environment](#setting-up-your-environment)
- [Scripts and Tools](#scripts-and-tools)
  - [Builder Scripts](#builder-scripts)
  - [Entrypoint](#entrypoint)
  - [Utility Scripts](#utility-scripts)
- [Advanced Configuration](#advanced-configuration)
- [Contributing](#contributing)
- [License](#license)

## Overview

This repository provides the necessary tools and scripts to build Odoo Community and Enterprise Docker containers. The intent is to streamline the process of generating containers that are tailored to your specific needs, ensuring that addons are up to date and preventing collisions.

**Note:** The Odoo Enterprise code is proprietary and cannot be distributed. Therefore, the generated containers from this repository are not available publicly.

## Disclaimer

- **Licensing Requirements:** Odoo Enterprise is a commercial product with specific licensing restrictions. You must comply with Odoo's licensing terms to use the Enterprise features.
- **No Public Distribution:** The generated containers include licensed code and, as such, cannot be shared or distributed publicly.
- **Self-Hosted Builds:** You are responsible for the costs and time involved in setting up your own environment to build the containers.

## Getting Started

### Prerequisites

Before you begin, ensure you have met the following requirements:

- **Docker and Docker Compose:** Installed and configured on your system.
- **GitHub Account:** Necessary for forking the repository and accessing private repositories.
- **Odoo Enterprise License:** Required to access the Odoo Enterprise code.

**Important:** This is not a beginner's setup. Familiarity with Docker, Git, and Odoo deployments is assumed. Additionally, this setup requires **Redis**, which is not always used with Odoo by default.

### Forking the Repository

To generate your own containers, you need to fork this repository:

1. Navigate to [github.com/aperim/container-odoo-base](https://github.com/aperim/container-odoo-base).
2. Click the **Fork** button in the top-right corner.
3. Clone your forked repository to your local machine:

   ```bash
   git clone https://github.com/<your-username>/container-odoo-base.git
   ```

### Setting Up Your Environment

1. **Configure Environment Variables:**

   Create a copy of the provided `.env.example` file and rename it to `.env`. Update the variables as needed, including your Odoo version, GitHub credentials, and Odoo repositories.

   ```bash
   cp .env.example .env
   ```

2. **Install Required Tools:**

   Ensure you have Python 3 installed along with the necessary packages:

   ```bash
   pip install -r requirements.txt
   ```

3. **Set Up GitHub Access:**

   - Generate a GitHub Personal Access Token (PAT) with appropriate scopes to access private repositories if necessary.
   - Update the `GITHUB_TOKEN` variable in your `.env` file with your PAT.

4. **Run the Builder Script:**

   Use the main builder script to set up the Odoo directories and clone the necessary repositories.

   ```bash
   python builder/src/main.py
   ```

## Scripts and Tools

This repository includes various scripts that facilitate container management and ensure that addons are up to date while preventing collisions.

### Builder Scripts

- **Main Builder (`builder/src/main.py`):** Sets up Odoo directories and clones the Odoo Community and Enterprise repositories, along with any additional addons specified.

- **GeoIP Updater (`builder/src/geoip_updater.py`):** Updates the GeoIP databases required by Odoo for geolocation features.

### Entrypoint

- **Entrypoint Script (`entrypoint/entrypoint.sh`):** The entrypoint script that manages the startup of the Odoo container. It performs several critical functions:

  - **Redis Integration:** Configures Redis as the session store and cache, which is essential for this container setup.
  - **Addon Management:** Ensures that shipped Odoo addons are present and up to date across community, enterprise, and extras.
  - **Collision Prevention:** Uses file locking mechanisms to prevent race conditions during initialization.
  - **Database Initialization:** Handles the creation and migration of the Odoo database.
  - **Signal Handling:** Properly handles system signals for graceful shutdown and cleanup.

### Utility Scripts

- **Addon Updater (`tools/src/addon_updater.py`):** Synchronises addons from the source directories to the target directories, ensuring consistency.

- **Lock Handler (`tools/src/lock_handler.py`):** Manages Redis-based locking to coordinate actions between multiple container instances.

- **Wait for Postgres (`tools/src/wait_for_postgres.py`):** Waits for PostgreSQL (and optionally PGBouncer) to become available before starting Odoo.

- **Odoo Config Manager (`tools/src/odoo_config.py`):** Manages the `odoo.conf` configuration file, allowing for dynamic configuration based on environment variables.

- **Healthcheck Scripts:**

  - **Websocket Checker (`tools/src/websocket_checker.py`):** Checks the availability of the WebSocket interface.
  - **Full Healthcheck (`tools/src/healthcheck_full.py`):** Performs comprehensive health checks on both the web and WebSocket services.

- **Backup and Restore Scripts:**

  - **Backup (`backup/backup.sh`):** Facilitates backing up the Odoo database and filestore.
  - **Restore (`backup/restore.sh`):** Handles restoration from backups.

## Advanced Configuration

This container setup is designed for advanced users who require a high degree of control and customization. Some key points:

- **Redis Requirement:** This container relies on Redis for session storage and caching. Ensure that you have a Redis instance available and properly configured.

- **Custom Addons:** You can include custom addons by specifying them in the `EXTRAS` variable within the builder script. Make sure to handle private repositories correctly by providing appropriate access tokens.

- **Database SSL/TLS:** Support for secure connections to PostgreSQL is included. Configure the SSL-related environment variables as needed.

- **Signal Handling and Cleanup:** The scripts are designed to handle unexpected shutdowns gracefully, ensuring locks are released and resources are cleaned up.

## Contributing

Contributions are welcome! Please ensure that any code you submit adheres to the following:

- **Coding Standards:** Follow the [Google Style Guides](https://google.github.io/styleguide/) for Python and Bash.
- **Typing and Documentation:** All code should be fully typed where applicable and well-documented.
- **Exceptions and Signals:** Handle exceptions and system signals properly to ensure robustness.
- **Licensing:** Ensure that all contributions comply with licensing requirements.

## License

This project is licensed under the **Apache License 2.0** - see the [LICENSE](LICENSE) file for details.

**Note:** While the repository is Apache 2.0 licensed, Odoo Enterprise is commercial software with its own licensing terms. You must comply with Odoo's licensing when using the Enterprise features.

---

For any issues or questions, please open an issue in the repository or contact the maintainers.
