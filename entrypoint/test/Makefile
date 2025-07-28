# Makefile for entrypoint testing
.PHONY: help test test-basic test-full test-destroy test-upgrade test-odoo shell logs clean reset

# Default target
help:
	@echo "Entrypoint Testing Commands:"
	@echo ""
	@echo "  make test          - Run all basic tests"
	@echo "  make test-basic    - Run basic functionality test"
	@echo "  make test-full     - Test full initialization"
	@echo "  make test-destroy  - Test destroy functionality"
	@echo "  make test-upgrade  - Test upgrade detection"
	@echo "  make test-odoo     - Run tests with real Odoo container"
	@echo "  make shell         - Start interactive debugging shell"
	@echo "  make logs          - Show container logs"
	@echo "  make clean         - Stop and remove all test containers"
	@echo "  make reset         - Reset test environment"
	@echo ""
	@echo "Examples:"
	@echo "  make test          # Run all tests"
	@echo "  make shell         # Debug interactively"
	@echo "  make test-odoo     # Test with real Odoo"

# Run all basic tests
test: test-basic test-full test-destroy test-upgrade
	@echo "✅ All basic tests completed"

# Individual test targets
test-basic:
	@echo "🧪 Testing basic functionality..."
	@./test-entrypoint.sh -m basic

test-full:
	@echo "🧪 Testing full initialization..."
	@./test-entrypoint.sh -m full

test-destroy:
	@echo "🧪 Testing destroy functionality..."
	@./test-entrypoint.sh -m destroy

test-upgrade:
	@echo "🧪 Testing upgrade detection..."
	@./test-entrypoint.sh -m upgrade

test-custom:
	@echo "🧪 Testing custom commands..."
	@./test-entrypoint.sh -m custom

# Test with real Odoo
test-odoo:
	@echo "🧪 Testing with real Odoo container..."
	@./test-with-odoo.sh

# Interactive shell
shell:
	@echo "🔧 Starting interactive shell..."
	@./test-entrypoint.sh shell

# View logs
logs:
	@./test-entrypoint.sh logs

# Clean up
clean:
	@echo "🧹 Cleaning up test environment..."
	@./test-entrypoint.sh down

# Reset environment
reset:
	@echo "♻️  Resetting test environment..."
	@./test-entrypoint.sh reset

# Quick test for development
quick:
	@echo "⚡ Running quick test..."
	@./test-entrypoint.sh test odoo --version