#!/usr/bin/env python3
import argparse
import sys
import os

# Add the parent directory to the path so we can import the app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from app.modules.db.migration_manager import create_migrations_table, migrate, rollback, create_migration, list_migrations

def main():
    parser = argparse.ArgumentParser(description='Database migration tool')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Create migration command
    create_parser = subparsers.add_parser('create', help='Create a new migration')
    create_parser.add_argument('name', help='Name of the migration')
    
    # Migrate command
    migrate_parser = subparsers.add_parser('migrate', help='Apply pending migrations')
    
    # Rollback command
    rollback_parser = subparsers.add_parser('rollback', help='Rollback migrations')
    rollback_parser.add_argument('--steps', type=int, default=1, help='Number of migrations to roll back')
    
    # Initialize command
    init_parser = subparsers.add_parser('init', help='Initialize the migrations table')

    # list command
    subparsers.add_parser('list', help='List all migrations and their status')
    
    args = parser.parse_args()
    
    if args.command == 'create':
        filename = create_migration(args.name)
        print(f"Created migration file: {filename}")
    elif args.command == 'migrate':
        success = migrate()
        if success:
            print("Migrations applied successfully")
        else:
            print("Error applying migrations")
            sys.exit(1)
    elif args.command == 'rollback':
        success = rollback(args.steps)
        if success:
            print(f"Rolled back {args.steps} migration(s) successfully")
        else:
            print("Error rolling back migrations")
            sys.exit(1)
    elif args.command == 'list':
        list_migrations()
    elif args.command == 'init':
        create_migrations_table()
        print("Migrations table initialized")
    else:
        parser.print_help()
        sys.exit(1)

if __name__ == '__main__':
    main()