#!/usr/bin/env python
"""
Vercel build entry point for the MarketIntel Django backend.

Behaviour:
  - Always runs `python manage.py check --deploy` (fails build on errors).
  - Runs `python manage.py migrate --noinput` ONLY when
    RUN_MIGRATIONS_ON_BUILD=true is set in the Vercel environment.

This ensures Preview deployments never accidentally migrate the
production Supabase database unless explicitly configured.
"""
import os
import subprocess
import sys


def run(*args):
    """Run a Django management command and raise on non-zero exit."""
    cmd = [sys.executable, 'manage.py'] + list(args)
    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd)


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

    # Always validate the deployment configuration.
    run('check', '--deploy')

    run_migrations = (
        os.environ.get('RUN_MIGRATIONS_ON_BUILD', 'false').strip().lower() == 'true'
    )

    if run_migrations:
        print("RUN_MIGRATIONS_ON_BUILD=true  →  Running database migrations…")
        run('migrate', '--noinput')
    else:
        print(
            "RUN_MIGRATIONS_ON_BUILD is false or unset  →  Skipping migrations.\n"
            "Set RUN_MIGRATIONS_ON_BUILD=true in Vercel env vars to apply migrations."
        )


if __name__ == '__main__':
    main()
