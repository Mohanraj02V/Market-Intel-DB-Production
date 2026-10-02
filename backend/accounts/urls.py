from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .views import UserMeView, UserViewSet, MailAccountViewSet

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'mail-account', MailAccountViewSet, basename='mail-account')


class LogoutView(APIView):
    """
    Server-side logout endpoint.

    Accepts the refresh token and blacklists it so it cannot be
    used to generate new access tokens. The client should also
    clear its local token storage on logout.

    POST /api/auth/logout/
    Body: { "refresh": "<refresh_token>" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"detail": "Refresh token required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception as exc:
            # Log the error but don't reveal whether the token was valid.
            import logging
            logging.getLogger(__name__).warning("Logout token blacklist error: %s", exc)

        # Write WhatsApp audit log for the logout action.
        try:
            from whatsapp.models import WhatsAppAuditLog
            from whatsapp.services import _write_audit_log
            _write_audit_log(
                action=WhatsAppAuditLog.Action.AUTH_LOGOUT,
                performed_by=request.user,
                success=True,
                result_detail="User logged out via /auth/logout/",
            )
        except Exception:
            pass

        return Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)


urlpatterns = [
    path('', include(router.urls)),
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', UserMeView.as_view(), name='user_me'),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
]
