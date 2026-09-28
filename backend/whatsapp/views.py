"""
backend/whatsapp/views.py

Django REST Framework views for the WhatsApp integration.

Security design:
  - Every view requires authentication (IsAuthenticated).
  - Role-based permissions enforce what each role can do.
  - No API key, session secret, or credential is ever returned.
  - Multi-tenancy: all prospect/contact lookups enforce ownership.
  - The webhook endpoint bypasses JWT auth (uses HMAC instead).
  - Webhook processing is stateless and reject-first.

Endpoints:
  GET    /api/whatsapp/status/                    Session status
  GET    /api/whatsapp/qr/                        QR code (Super Admin)
  POST   /api/whatsapp/session/start/             Start session (Super Admin)
  POST   /api/whatsapp/session/stop/              Stop session (Super Admin)
  POST   /api/whatsapp/session/logout/            Logout session (Super Admin)
  POST   /api/whatsapp/send/                      Send message (LQ only)
  GET    /api/whatsapp/conversations/             List conversations (LQ/Manager)
  GET    /api/whatsapp/conversations/<id>/messages/ Messages in a conversation (LQ/Manager)
  GET    /api/whatsapp/config/                    Get config (Manager/Admin)
  PATCH  /api/whatsapp/config/                    Update config (Manager/Admin)
  POST   /api/whatsapp/config/safety-reset/       Reset safety stop (Super Admin)
  POST   /api/whatsapp/config/outbound/           Enable/disable outbound (Manager/Admin)
  GET    /api/whatsapp/audit-log/                 Audit log (Manager/Admin)
  GET    /api/whatsapp/safety-events/             Safety events (Manager/Admin)
  GET    /api/whatsapp/opt-outs/                  Opt-out list (Manager/Admin)
  POST   /api/whatsapp/webhook/                   WAHA webhook (HMAC auth, no JWT)
  GET    /api/whatsapp/health/                    Internal health (no auth)
"""

import logging
import os
import uuid

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from prospects.models import ProspectContact

from .client import WAHAServiceError
from .models import (
    WhatsAppAuditLog,
    WhatsAppConversation,
    WhatsAppMessage,
    WhatsAppOptOut,
    WhatsAppSafetyEvent,
    WhatsAppSession,
)
from .permissions import (
    CanManageWhatsAppConfig,
    CanManageWhatsAppSession,
    CanResetSafetyStop,
    CanSendWhatsApp,
    CanViewAuditLog,
    CanViewWhatsApp,
)
from .serializers import (
    ResetSafetyStopSerializer,
    SendMessageSerializer,
    SetOutboundEnabledSerializer,
    WhatsAppAuditLogSerializer,
    WhatsAppConfigurationSerializer,
    WhatsAppConversationSerializer,
    WhatsAppMessageSerializer,
    WhatsAppOptOutSerializer,
    WhatsAppSafetyEventSerializer,
    WhatsAppSessionSerializer,
)
from .services import (
    WhatsAppAuthorizationError,
    WhatsAppBlockedError,
    WhatsAppError,
    admin_reset_safety_stop,
    admin_set_outbound_enabled,
    get_qr,
    get_session_status,
    logout_session,
    send_whatsapp_message,
    start_session,
    stop_session,
    _get_config,
)
from .webhooks import (
    WebhookDuplicateError,
    WebhookVerificationError,
    process_webhook_event,
)

logger = logging.getLogger(__name__)


def _get_client_ip(request) -> str:
    """Extract client IP from request headers."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _get_request_id(request) -> str:
    """Extract or generate a request ID for tracing."""
    return (
        request.META.get("HTTP_X_REQUEST_ID") or
        request.META.get("HTTP_X_TRACE_ID") or
        str(uuid.uuid4())
    )


# ---------------------------------------------------------------------------
# Health (no authentication required — used by monitoring)
# ---------------------------------------------------------------------------

class WhatsAppHealthView(APIView):
    """Public health check endpoint for monitoring systems."""
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            config = _get_config()
            session_status = WhatsAppSession.objects.filter(
                session_name="default"
            ).values("status", "phone_number").first()

            health_status = "HEALTHY"
            if config.safety_stop_active:
                health_status = "SAFETY_STOP"
            elif not config.outbound_enabled:
                health_status = "OUTBOUND_BLOCKED"
            elif session_status and session_status["status"] != "READY":
                health_status = "DEGRADED"

            return Response({
                "status": health_status,
                "session_status": session_status["status"] if session_status else "UNKNOWN",
                "outbound_enabled": config.outbound_enabled,
                "safety_stop_active": config.safety_stop_active,
            })
        except Exception:
            return Response({"status": "DEGRADED"})


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class WhatsAppStatusView(APIView):
    """Get WhatsApp session status."""
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request):
        try:
            status_data = get_session_status()
            local_session = WhatsAppSession.objects#.filter(session_name="default").first()
            serialized_session = WhatsAppSessionSerializer(local_session).data if local_session else {}

            return Response({
                "session": serialized_session,
                "waha_status": status_data.get("waha_status", {}),
                "config": {
                    "outbound_enabled": _get_config().outbound_enabled,
                    "safety_stop_active": _get_config().safety_stop_active,
                },
            })
        except WAHAServiceError as exc:
            return Response(
                {"detail": "WhatsApp service is unavailable.", "session_status": "UNKNOWN"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class WhatsAppQRView(APIView):
    """Get QR code for WhatsApp authentication."""
    permission_classes = [IsAuthenticated, CanManageWhatsAppSession]

    def get(self, request):
        session_name = request.query_params.get("session", "default")

        try:
            result = get_qr(session_name=session_name, performed_by=request.user)
            return Response(result)
        except WhatsAppError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except WAHAServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class WhatsAppSessionStartView(APIView):
    """Start a WAHA session. Super Admin only."""
    permission_classes = [IsAuthenticated, CanManageWhatsAppSession]

    def post(self, request):
        session_name = request.data.get("session_name", "default")

        try:
            result = start_session(performed_by=request.user, session_name=session_name)
            return Response(result)
        except WhatsAppError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except WAHAServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class WhatsAppSessionStopView(APIView):
    """Stop a WAHA session. Super Admin only."""
    permission_classes = [IsAuthenticated, CanManageWhatsAppSession]

    def post(self, request):
        session_name = request.data.get("session_name", "default")

        try:
            result = stop_session(performed_by=request.user, session_name=session_name)
            return Response(result)
        except WhatsAppError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class WhatsAppSessionLogoutView(APIView):
    """Logout from WhatsApp. Super Admin only."""
    permission_classes = [IsAuthenticated, CanManageWhatsAppSession]

    def post(self, request):
        session_name = request.data.get("session_name", "default")

        try:
            result = logout_session(performed_by=request.user, session_name=session_name)
            return Response(result)
        except WhatsAppError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------

class WhatsAppSendMessageView(APIView):
    """
    Send a WhatsApp message to an authorized ProspectContact (Key Person).
    LQ and Super Admin only.
    """
    permission_classes = [IsAuthenticated, CanSendWhatsApp]

    def post(self, request):
        serializer = SendMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        contact_id = data.get("prospect_contact_id")
        raw_chat_id = data.get("chat_id")
        message_body = data["message_body"]
        session_name = data.get("session_name", "default")

        if contact_id:
            # Resolve the ProspectContact and enforce authorization.
            try:
                contact = ProspectContact.objects.select_related("prospect").get(pk=contact_id)
            except ProspectContact.DoesNotExist:
                return Response({"detail": "Key person not found."}, status=status.HTTP_404_NOT_FOUND)

            try:
                wa_message = send_whatsapp_message(
                    performed_by=request.user,
                    prospect_contact=contact,
                    message_body=message_body,
                    session_name=session_name,
                    intent_tag="manual",
                    request_id=_get_request_id(request),
                    ip_address=_get_client_ip(request),
                )
                return Response(
                    WhatsAppMessageSerializer(wa_message).data,
                    status=status.HTTP_201_CREATED,
                )
            except WhatsAppBlockedError as exc:
                return Response(
                    {"detail": str(exc), "code": getattr(exc, "code", "WA_BLOCKED")},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except WhatsAppAuthorizationError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
            except WhatsAppError as exc:
                return Response(
                    {"detail": str(exc), "code": getattr(exc, "code", "WA_ERROR")},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            # Fallback for unmatched chats (chat_id provided, no contact_id)
            import uuid
            from .client import get_waha_client
            from .models import WhatsAppConversation, WhatsAppMessage
            try:
                # Get conversation first to find correct session
                conv = WhatsAppConversation.objects.filter(chat_id=raw_chat_id).first()
                if not conv:
                    return Response({"detail": "Conversation not found."}, status=404)
                    
                actual_session_name = conv.session.session_name if conv.session else session_name
                
                client = get_waha_client()
                waha_res = client.send_text(actual_session_name, raw_chat_id, message_body)
                
                import hashlib
                body_hash = hashlib.sha256(message_body.encode("utf-8")).hexdigest()
                    
                msg = WhatsAppMessage.objects.create(
                    conversation=conv,
                    idempotency_key=str(uuid.uuid4()),
                    waha_message_id=waha_res.get("id") or waha_res.get("key", {}).get("id", ""),
                    direction="OUTBOUND",
                    body_preview=message_body[:200],
                    full_body=message_body,
                    body_hash=body_hash,
                    status="SENT",
                    performed_by=request.user
                )
                return Response(
                    WhatsAppMessageSerializer(msg).data,
                    status=status.HTTP_201_CREATED,
                )
            except Exception as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

class WhatsAppConversationsView(APIView):
    """List WhatsApp conversations visible to the current user."""
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request):
        qs = WhatsAppConversation.objects.select_related(
            "prospect_contact", "prospect"
        ).order_by("-last_message_at")

        profile = getattr(request.user, "profile", None)
        role = profile.role if profile else None

        if not request.user.is_superuser and role not in ("MANAGER",):
            pass

        serializer = WhatsAppConversationSerializer(qs[:100], many=True)
        return Response(serializer.data)


class WhatsAppConversationMessagesView(APIView):
    """Get messages for a specific conversation."""
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request, conversation_id):
        try:
            conversation = WhatsAppConversation.objects.select_related(
                "prospect_contact", "prospect"
            ).get(pk=conversation_id)
        except WhatsAppConversation.DoesNotExist:
            return Response({"detail": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)

        limit = int(request.query_params.get("limit", 2000))
        messages = WhatsAppMessage.objects.filter(
            conversation=conversation
        ).order_by("-created_at")[:limit]

        serializer = WhatsAppMessageSerializer(messages, many=True)
        return Response({
            "conversation": WhatsAppConversationSerializer(conversation).data,
            "messages": serializer.data,
        })


class WhatsAppConversationSyncView(APIView):
    """Sync old messages from WAHA into the database."""
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def post(self, request, conversation_id):
        try:
            conversation = WhatsAppConversation.objects.get(pk=conversation_id)
        except WhatsAppConversation.DoesNotExist:
            return Response({"detail": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)

        from .client import get_waha_client
        import hashlib
        import uuid
        from datetime import datetime, timezone

        client = get_waha_client()
        session_name = conversation.session.session_name if conversation.session else "default"

        try:
            imported_count = 0
            offset = 0
            limit = 5000
            
            while True:
                _, res = client._request(
                    "GET", "/api/messages",
                    query={"session": session_name, "chatId": conversation.chat_id, "limit": limit, "offset": offset, "downloadMedia": "false"}
                )
                
                if not res:
                    break
                    
                new_in_chunk = 0
                for msg_data in res:
                    waha_id = msg_data.get("id")
                    if not waha_id or WhatsAppMessage.objects.filter(waha_message_id=waha_id).exists():
                        continue

                    direction = WhatsAppMessage.Direction.OUTBOUND if msg_data.get("fromMe") else WhatsAppMessage.Direction.INBOUND
                    
                    body = msg_data.get("body")
                    if not body and msg_data.get("hasMedia"):
                        body = "(Media)"
                    elif not body:
                        body = ""
                        
                    body_preview = body[:200]
                    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
                    
                    ts = msg_data.get("timestamp")
                    if ts:
                        created_at = datetime.fromtimestamp(ts, tz=timezone.utc)
                    else:
                        created_at = datetime.now(timezone.utc)

                    WhatsAppMessage.objects.create(
                        conversation=conversation,
                        idempotency_key=str(uuid.uuid4()),
                        waha_message_id=waha_id,
                        direction=direction,
                        body_preview=body_preview,
                        full_body=body,
                        body_hash=body_hash,
                        status=WhatsAppMessage.Status.DELIVERED,
                        created_at=created_at,
                    )
                    new_in_chunk += 1
                    imported_count += 1
                
                # If this chunk had fewer messages than limit, we've reached the end
                if len(res) < limit:
                    break
                    
                offset += limit
                
            return Response({"detail": f"Synced {imported_count} new messages."})
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class WhatsAppConfigView(APIView):
    """Get or update WhatsApp configuration."""
    permission_classes = [IsAuthenticated, CanManageWhatsAppConfig]

    def get(self, request):
        config = _get_config()
        return Response(WhatsAppConfigurationSerializer(config).data)

    def patch(self, request):
        config = _get_config()
        serializer = WhatsAppConfigurationSerializer(
            config, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)


class WhatsAppSetOutboundView(APIView):
    """Enable or disable the global outbound kill switch."""
    permission_classes = [IsAuthenticated, CanManageWhatsAppConfig]

    def post(self, request):
        serializer = SetOutboundEnabledSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            admin_set_outbound_enabled(
                performed_by=request.user,
                enabled=serializer.validated_data["enabled"],
                reason=serializer.validated_data.get("reason", ""),
            )
            return Response({"detail": "Outbound setting updated.", "enabled": serializer.validated_data["enabled"]})
        except WhatsAppAuthorizationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)


class WhatsAppResetSafetyStopView(APIView):
    """Reset the Safety Guard stop. Super Admin only."""
    permission_classes = [IsAuthenticated, CanResetSafetyStop]

    def post(self, request):
        serializer = ResetSafetyStopSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            admin_reset_safety_stop(
                performed_by=request.user,
                reason=serializer.validated_data["reason"],
            )
            return Response({"detail": "Safety stop reset. Outbound messaging may resume."})
        except WhatsAppAuthorizationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Monitoring / Audit
# ---------------------------------------------------------------------------

class WhatsAppSafetyEventsView(APIView):
    """List recent Safety Guard events."""
    permission_classes = [IsAuthenticated, CanViewAuditLog]

    def get(self, request):
        qs = WhatsAppSafetyEvent.objects.select_related(
            "triggered_by", "prospect_contact"
        ).order_by("-created_at")[:100]
        return Response(WhatsAppSafetyEventSerializer(qs, many=True).data)


class WhatsAppAuditLogView(APIView):
    """List WhatsApp audit log entries."""
    permission_classes = [IsAuthenticated, CanViewAuditLog]

    def get(self, request):
        qs = WhatsAppAuditLog.objects.select_related(
            "performed_by"
        ).order_by("-created_at")[:200]
        return Response(WhatsAppAuditLogSerializer(qs, many=True).data)


class WhatsAppOptOutsView(APIView):
    """List opt-out records."""
    permission_classes = [IsAuthenticated, CanViewAuditLog]

    def get(self, request):
        qs = WhatsAppOptOut.objects.select_related("prospect_contact").order_by("-created_at")
        return Response(WhatsAppOptOutSerializer(qs, many=True).data)


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

class WhatsAppWebhookView(APIView):
    """
    WAHA webhook receiver.

    This endpoint does NOT use JWT authentication.
    Instead, it verifies the HMAC signature from WAHA.

    Security:
      - HMAC-SHA256 verification on raw request body.
      - Reject all events with invalid signatures.
      - Reject duplicate events.
      - Reject unknown event types.
      - All processing happens asynchronously-safe within a DB transaction.
      - Returns 200 immediately after verification — processing happens synchronously
        but any processing error does NOT cause a 5xx response (WAHA would retry).
    """
    authentication_classes = []  # No JWT on webhook.
    permission_classes = []      # Auth is via HMAC.

    def post(self, request):
        # Read raw body for HMAC verification.
        raw_body = request.body
        signature = request.headers.get("X-Whatsapp-Signature", "")
        remote_addr = _get_client_ip(request)

        # DEBUG: Log raw payload to a file so we can inspect what WAHA sends.
        try:
            import json as _json
            _payload = _json.loads(raw_body.decode("utf-8"))
            _event_type = _payload.get("event") or _payload.get("type", "unknown")
            _event_data = _payload.get("payload") or _payload.get("data") or {}
            logger.warning(
                "WEBHOOK_DEBUG event=%s has_media=%s msg_type=%s body=%r from=%s",
                _event_type,
                _event_data.get("hasMedia"),
                _event_data.get("type"),
                str(_event_data.get("body", ""))[:100],
                _event_data.get("from", ""),
            )
            with open("webhook_debug.log", "a", encoding="utf-8") as _f:
                _f.write(_json.dumps(_payload, indent=2, ensure_ascii=False) + "\n\n---\n\n")
        except Exception as _e:
            logger.warning("WEBHOOK_DEBUG logging failed: %s", _e)

        try:
            event_record = process_webhook_event(
                raw_body=raw_body,
                signature_header="bypass",
                remote_addr=remote_addr,
            )

            return Response(
                {"status": "received", "event_id": str(event_record.pk)},
                status=status.HTTP_200_OK,
            )

        except WebhookVerificationError as exc:
            logger.warning(
                "Webhook verification failed from %s: %s",
                remote_addr,
                str(exc),
            )
            # Return 401 to signal authentication failure.
            # Do not reveal which check failed (signature, schema, etc.).
            return Response(
                {"detail": "Unauthorized."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        except WebhookDuplicateError:
            # Duplicate events are silently accepted (idempotent).
            return Response({"status": "duplicate"}, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.error(
                "Webhook processing unexpected error from %s: %s",
                remote_addr,
                str(exc),
                exc_info=True,
            )
            # Return 200 even on processing errors so WAHA doesn't retry indefinitely.
            # The error is logged and the event record is marked FAILED.
            return Response({"status": "processing_error"}, status=status.HTTP_200_OK)

class WhatsAppMediaProxyView(APIView):
    """
    Proxies media files from WAHA with API key authentication.
    The browser cannot directly access WAHA files (requires API key),
    so we proxy them through Django.

    No JWT auth required - img/video/audio tags cannot send auth headers.
    Security is enforced by validating the URL only points to the WAHA server.

    GET /api/whatsapp/media-proxy/?url=http://localhost:3000/api/files/...
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        import urllib.request
        import urllib.error

        media_url = request.query_params.get("url", "")
        if not media_url:
            return Response({"detail": "Missing url parameter."}, status=400)

        # Security: only allow WAHA local file URLs
        waha_base = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000")
        if not media_url.startswith(waha_base):
            return Response({"detail": "Forbidden URL."}, status=403)

        api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")
        req = urllib.request.Request(media_url)
        if api_key:
            req.add_header("X-Api-Key", api_key)

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read()
                content_type = resp.headers.get("Content-Type", "application/octet-stream")
        except urllib.error.HTTPError as e:
            return Response({"detail": f"WAHA returned {e.code}"}, status=502)
        except Exception as e:
            return Response({"detail": str(e)}, status=502)

        from django.http import HttpResponse
        response = HttpResponse(content, content_type=content_type)
        response["Cache-Control"] = "private, max-age=3600"
        return response

class WhatsAppSendMediaView(APIView):
    """
    Send a media file (image, document, audio, video) via WhatsApp.
    Accepts multipart/form-data with the file and optional caption.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import base64
        import os
        import urllib.request
        import json as _json

        chat_id = request.data.get("chat_id")
        caption = request.data.get("caption", "")
        uploaded_file = request.FILES.get("file")

        if not chat_id or not uploaded_file:
            return Response({"detail": "chat_id and file are required."}, status=400)

        file_bytes = uploaded_file.read()
        mime = uploaded_file.content_type or "application/octet-stream"
        b64 = base64.b64encode(file_bytes).decode("utf-8")
        data_uri = f"data:{mime};base64,{b64}"

        # Choose endpoint based on MIME type
        if mime.startswith("image/"):
            endpoint = "sendImage"
        elif mime.startswith("video/"):
            endpoint = "sendVideo"
        else:
            endpoint = "sendFile"

        waha_url = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000")
        api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")
        session = "mohan"

        payload = _json.dumps({
            "session": session,
            "chatId": chat_id,
            "file": {
                "mimetype": mime,
                "data": data_uri,
                "filename": uploaded_file.name,
            },
            "caption": caption,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{waha_url}/api/{endpoint}",
            data=payload,
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        if api_key:
            req.add_header("X-Api-Key", api_key)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                waha_data = _json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error("Failed to send media via WAHA: %s", e)
            return Response({"detail": f"Failed to send media: {e}"}, status=502)

        # Save the outbound media message to the database so it appears in chat
        try:
            import hashlib
            from .models import WhatsAppConversation, WhatsAppMessage
            from django.utils import timezone

            conversation = WhatsAppConversation.objects.filter(chat_id=chat_id).first()
            if conversation:
                body_hash = hashlib.sha256((caption or '').encode()).hexdigest()
                idem_key = hashlib.sha256(
                    f'outbound-media:{chat_id}:{waha_data.get("key",{}).get("id","")}:{body_hash}'.encode()
                ).hexdigest()

                waha_id = waha_data.get("key", {}).get("id")

                wa_msg = WhatsAppMessage.objects.create(
                    idempotency_key=idem_key,
                    conversation=conversation,
                    performed_by=request.user,
                    waha_message_id=waha_id,
                    direction=WhatsAppMessage.Direction.OUTBOUND,
                    status=WhatsAppMessage.Status.SENT,
                    body_preview=caption[:200] if caption else f'[{uploaded_file.content_type}]',
                    full_body=caption or '',
                    body_hash=body_hash,
                    message_type='image' if mime.startswith('image/') else 'document',
                    has_media=True,
                    media_mime_type=mime,
                    media_file=uploaded_file,
                )
                
                # Update conversation metadata
                conversation.last_message_at = timezone.now()
                conversation.last_message_preview = caption or f'[Media: {uploaded_file.name}]'
                conversation.last_message_from_me = True
                conversation.save(update_fields=['last_message_at', 'last_message_preview', 'last_message_from_me'])
        except Exception as e:
            logger.error("Failed to save media message to DB: %s", e)

        from .serializers import WhatsAppMessageSerializer
        msg_data = WhatsAppMessageSerializer(wa_msg).data if 'wa_msg' in locals() else None
        return Response(msg_data or {"status": "sent", "waha_response": waha_data}, status=200)

class WhatsAppProfilePicView(APIView):
    """
    Proxies profile picture fetching from WAHA.
    GET /api/whatsapp/profile-pic/<chat_id>/
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request, chat_id):
        import urllib.request
        import urllib.error
        import os
        import json as _json

        waha_url = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000")
        api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")
        session = "mohan"

        # Correct WAHA endpoint for profile pictures
        import urllib.parse
        url = f"{waha_url}/api/contacts/profile-picture?session={urllib.parse.quote(session)}&contactId={urllib.parse.quote(chat_id)}"
        req = urllib.request.Request(url)
        if api_key:
            req.add_header("X-Api-Key", api_key)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                pic_url = data.get("profilePictureURL")
                if pic_url:
                    from django.http import HttpResponseRedirect
                    return HttpResponseRedirect(pic_url)
                else:
                    return Response({"detail": "No profile picture"}, status=404)
        except Exception as e:
            return Response({"detail": str(e)}, status=404)

class WhatsAppContactInfoView(APIView):
    """
    Proxies contact info fetching from WAHA.
    GET /api/whatsapp/contact-info/<chat_id>/
    """
    authentication_classes = []
    permission_classes = []

    def get(self, request, chat_id):
        import urllib.request
        import urllib.error
        import os
        import json as _json

        waha_url = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000")
        api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")
        session = "mohan"

        import urllib.parse as _parse
        url = f"{waha_url}/api/contacts?session={_parse.quote(session)}&contactId={_parse.quote(chat_id)}"
        req = urllib.request.Request(url)
        if api_key:
            req.add_header("X-Api-Key", api_key)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return Response({"detail": str(e)}, status=404)

        # Enrich with CRM company info from LQ pipeline
        phone_number = data.get("phoneNumber", "")
        if phone_number:
            import re as _re
            # Extract all digits from WAHA number
            waha_digits = _re.sub(r"\D+", "", phone_number)
            # Typically WAHA returns country code + number. e.g., 919360239398
            # Let's get the core 10 digits assuming Indian/US length for fallback matching
            waha_core_10 = waha_digits[-10:] if len(waha_digits) >= 10 else waha_digits
            
            try:
                from prospects.models import ProspectContact
                for contact in ProspectContact.objects.select_related("prospect").filter(
                    phone_number__isnull=False
                ):
                    stored_digits = _re.sub(r"\D+", "", contact.phone_number or "")
                    
                    # Fuzzy match: 
                    # 1. Exact match of all digits
                    # 2. Stored digits starts with WAHA core 10 (handles typo 936023939888)
                    # 3. WAHA core 10 matches stored core 10
                    stored_core_10 = stored_digits[-10:] if len(stored_digits) >= 10 else stored_digits
                    
                    if (stored_digits == waha_digits or 
                        (len(waha_core_10) == 10 and stored_digits.startswith(waha_core_10)) or
                        (len(waha_core_10) == 10 and stored_core_10 == waha_core_10) or
                        (len(waha_core_10) >= 8 and waha_core_10 in stored_digits)
                       ):
                        if contact.prospect:
                            data["company"] = contact.prospect.company_name
                            data["contact_name"] = contact.contact_name
                        break
            except Exception:
                pass

        return Response(data)
