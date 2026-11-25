"""Tracked deterministic test settings for local and CI/CD test execution."""
import os
from cryptography.fernet import Fernet

os.environ.setdefault('DEBUG', 'True')
os.environ.setdefault('SECRET_KEY', 'ci-test-only-secret-key-not-for-production-use-0123456789')
os.environ.setdefault('MAIL_CREDENTIALS_ENCRYPTION_KEY', Fernet.generate_key().decode('ascii'))

from config.settings import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ['*']
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
EMAIL_TRACKING_BASE_URL = 'https://test-tracking.example.com'
GOOGLE_OAUTH_CLIENT_ID = 'ci-test-google-client-id.apps.googleusercontent.com'
GOOGLE_OAUTH_CLIENT_SECRET = 'ci-test-google-client-secret'
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
