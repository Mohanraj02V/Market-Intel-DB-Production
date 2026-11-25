"""Tracked deterministic test settings for local and CI/CD test execution."""
import os

os.environ.setdefault('DEBUG', 'True')
os.environ.setdefault('SECRET_KEY', 'ci-test-only-secret-key-not-for-production-use-0123456789')
os.environ.setdefault('MAIL_CREDENTIALS_ENCRYPTION_KEY', 'V2h5VGhpc0lzQVRlc3RPbmx5RmVybmV0S2V5MTIzNDU=')

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
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
