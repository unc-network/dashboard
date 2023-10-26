#!/usr/bin/sh
############################################################
# Run Django commands to modify the database on startup
############################################################
echo "Creating cache table if it does not exist..."
python3 manage.py createcachetable
echo "Migrating the database..."
python3 manage.py migrate

############################################################
# Run the Django app using gunicorn
############################################################
echo "Running gunicorn ${GUNICORN_CMD_ARGS} wsgi..."
# gunicorn --forwarded-allow-ips='*' --bind=0.0.0.0:8000 wsgi
# gunicorn --forwarded-allow-ips='*' --bind=0.0.0.0:8000 --access-logfile=- wsgi
gunicorn ${GUNICORN_CMD_ARGS} wsgi
