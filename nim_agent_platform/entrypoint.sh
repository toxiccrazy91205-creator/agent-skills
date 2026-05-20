#!/bin/sh

echo "Applying database migrations..."
python nim_agent_platform/manage.py migrate --noinput

echo "Collecting static files..."
python nim_agent_platform/manage.py collectstatic --noinput

echo "Starting Gunicorn server..."
exec gunicorn --bind 0.0.0.0:$PORT --chdir nim_agent_platform nim_agent_platform.wsgi:application
