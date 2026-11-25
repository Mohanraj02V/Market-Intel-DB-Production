from rest_framework import exceptions
from rest_framework.authentication import CSRFCheck
from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJWTAuthentication(JWTAuthentication):
    """
    Authenticates via Authorization: Bearer <token> header (CSRF-exempt),
    falling back to the HttpOnly access_token cookie with DRF CSRF enforcement
    on unsafe HTTP methods (POST/PUT/PATCH/DELETE).
    """

    def enforce_csrf(self, request):
        def dummy_get_response(req):
            return None

        check = CSRFCheck(dummy_get_response)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise exceptions.PermissionDenied(f'CSRF Failed: {reason}')

    def authenticate(self, request):
        # 1. Try standard Authorization: Bearer header (immune to CSRF)
        header = self.get_header(request)
        if header is not None:
            raw_token = self.get_raw_token(header)
            if raw_token is not None:
                try:
                    validated_token = self.get_validated_token(raw_token)
                    return self.get_user(validated_token), validated_token
                except Exception:
                    pass

        # 2. Fallback to access_token HttpOnly cookie (enforce CSRF on unsafe methods)
        raw_token = request.COOKIES.get('access_token')
        if raw_token is not None:
            try:
                validated_token = self.get_validated_token(raw_token)
                user = self.get_user(validated_token)
            except Exception:
                return None
            self.enforce_csrf(request)
            return user, validated_token

        return None
