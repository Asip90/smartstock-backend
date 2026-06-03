web: python manage.py migrate --noinput && python manage.py ensure_admin && gunicorn core.wsgi --bind 0.0.0.0:$PORT
