#!/usr/bin/env python3

"""
odoo_regenerate_assets.py - Regenerate Odoo assets by deleting specific records from ir_attachment

Author: Troy Kelly
Contact: troy@aperim.com
History:
    2024-10-03: Initial creation
"""

import os
import sys
import argparse
import psycopg2
from psycopg2 import sql


def delete_assets_from_ir_attachment(db_name: str) -> None:
    """
    Delete records from ir_attachment where res_model is 'ir.ui.view' and name contains 'assets_'.

    Args:
        db_name (str): The name of the database to connect to.
    """
    postgres_password = os.getenv('POSTGRES_PASSWORD')
    postgres_host = os.getenv('POSTGRES_HOST')
    postgres_user = os.getenv('POSTGRES_USER')

    if not all([postgres_password, postgres_host, postgres_user, db_name]):
        print("Error: Missing required environment variables or database name.", file=sys.stderr)
        sys.exit(1)

    try:
        connection = psycopg2.connect(
            dbname=db_name,
            user=postgres_user,
            password=postgres_password,
            host=postgres_host
        )
        cursor = connection.cursor()
        delete_query = sql.SQL(
            "DELETE FROM ir_attachment WHERE id IN "
            "(SELECT id FROM ir_attachment WHERE res_model='ir.ui.view' AND name LIKE '%assets_%');"
        )
        cursor.execute(delete_query)
        connection.commit()
        cursor.close()
        connection.close()
        print("Assets successfully deleted from ir_attachment.")
    except Exception as e:
        print(f"Error executing delete query: {e}", file=sys.stderr)
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        argparse.Namespace: The parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Regenerate Odoo assets by deleting specific records from ir_attachment"
    )
    parser.add_argument(
        'db_name',
        nargs='?',
        default=os.getenv('POSTGRES_DB'),
        help='The name of the database to connect to (default: value of POSTGRES_DB environment variable)'
    )
    return parser.parse_args()


def main() -> None:
    """Main function for script."""
    args = parse_args()
    delete_assets_from_ir_attachment(args.db_name)


if __name__ == "__main__":
    main()
