from rest_framework.permissions import BasePermission, SAFE_METHODS


class MarketEventPermission(BasePermission):
    """
    Permission class for Market Events:

    Safe methods (GET, HEAD, OPTIONS):
        Allowed for: PRE, LQ, superuser

    Mutation methods (POST, PUT, PATCH, DELETE):
        Allowed for: PRE, superuser
        Denied for:  LQ  → HTTP 403

    Unauthenticated requests are always denied.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_superuser:
            return True

        role = getattr(getattr(request.user, 'profile', None), 'role', None)

        if request.method in SAFE_METHODS:
            # PRE and LQ can read
            return role in ('PRE', 'LQ')

        # Only PRE can mutate
        return role == 'PRE'
