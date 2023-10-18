#!/usr/bin/sh
############################################################
# Run Django commands to modify the database on startup
############################################################
python3 manage.py createcachetable
python3 manage.py migrate

############################################################
# Run the Django app using gunicorn
############################################################
gunicorn --forwarded-allow-ips='*' --bind=0.0.0.0:8000 wsgi
