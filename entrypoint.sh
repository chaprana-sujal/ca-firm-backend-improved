#!/bin/sh

# Exit immediately if a command exits with a non-zero status.
set -e

# Run database migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# 3. NEW LINE: Run the script to create the superuser
echo "Creating superuser (if it doesn't exist)..."
python manage.py create_admin


# Start the Gunicorn server
# $PORT is automatically provided by Railway
echo "Starting Gunicorn server..."
gunicorn core.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 4

