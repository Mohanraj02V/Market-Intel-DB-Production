from rest_framework import permissions


def can_access_transcriptions(user) -> bool:
    """PRE, LQ, MANAGER users and superusers may access the Transcription module."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.role in ('PRE', 'LQ', 'MANAGER'))


def is_manager_or_superuser(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.role == 'MANAGER')


class CanAccessTranscriptions(permissions.BasePermission):
    message = 'You do not have permission to access meeting transcriptions.'

    def has_permission(self, request, view):
        return can_access_transcriptions(request.user)


class CanProcessPendingTranscriptions(permissions.BasePermission):
    message = 'Only Managers or Superusers can trigger batch transcription processing.'

    def has_permission(self, request, view):
        return is_manager_or_superuser(request.user)
