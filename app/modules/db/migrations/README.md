# Database Migrations

This directory contains database migration files for Roxy-WI. Each migration file represents a specific change to the database schema.

## Migration System

The migration system is designed to track which migrations have been applied, apply migrations in the correct order, and support rollbacks. It uses Peewee's migration functionality to make changes to the database schema.

## Migration Files

Each migration file is a Python module with two functions:

- `up()`: Applies the migration
- `down()`: Rolls back the migration

Migration files are named with a timestamp prefix to ensure they are applied in the correct order.

## Using the Migration System

The migration system provides a command-line interface for managing migrations. The following commands are available:

### Initialize the Migrations Table

```bash
python app/migrate.py init
```

This command creates the migrations table in the database if it doesn't exist.

### Create a New Migration

```bash
python app/migrate.py create <migration_name>
```

This command creates a new migration file with the given name. The file will be created in the migrations directory with a timestamp prefix.

### Apply Pending Migrations

```bash
python app/migrate.py migrate
```

This command applies all pending migrations in the correct order.

### Roll Back Migrations

```bash
python app/migrate.py rollback [--steps <number>]
```

This command rolls back the specified number of migrations (default: 1) in reverse order.

## Automatic Migrations

The migration system is automatically run when the application starts up. This ensures that the database schema is always up to date.

## Converting from the Old Update System

The old update system used multiple update functions in create_db.py to handle database schema changes. These functions have been converted to migration files in this directory. The application now uses the migration system instead of the old update functions.
