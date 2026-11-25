import json
import logging

from django.db.models import Q
from django.utils.dateparse import parse_date
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from transcriptions.models import MeetingTranscription
from transcriptions.permissions import CanAccessTranscriptions, CanProcessPendingTranscriptions
from transcriptions.serializers import (
    MeetingTranscriptionDetailSerializer,
    MeetingTranscriptionListSerializer,
)
from transcriptions.services import (
    fetch_and_store_zoom_transcript,
    handle_zoom_webhook_payload,
    process_pending_transcriptions,
    verify_zoom_webhook_signature,
)

logger = logging.getLogger(__name__)


class TranscriptionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class MeetingTranscriptionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    Read and operational endpoints for normalized meeting transcriptions.

    - GET /api/transcriptions/
    - GET /api/transcriptions/{id}/
    - POST /api/transcriptions/{id}/refresh/
    - POST /api/transcriptions/process-pending/
    """

    permission_classes = [CanAccessTranscriptions]
    pagination_class = TranscriptionPagination
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return MeetingTranscriptionDetailSerializer
        return MeetingTranscriptionListSerializer

    def get_queryset(self):
        user = self.request.user
        qs = MeetingTranscription.objects.select_related(
            'user', 'meeting', 'calendar_recording', 'automation_job'
        )

        # Role-based + company-level isolation matching existing CRM conventions:
        # - Superusers see all transcriptions
        # - Managers see transcriptions belonging to users in their company
        # - Standard users (PRE / LQ) see only their own transcriptions
        profile = getattr(user, 'profile', None)
        if user.is_superuser:
            pass
        elif profile and profile.role == 'MANAGER':
            if profile.company_id:
                qs = qs.filter(user__profile__company_id=profile.company_id)
            else:
                qs = qs.filter(user=user)
        else:
            qs = qs.filter(user=user)

        params = self.request.query_params

        provider = (params.get('provider') or '').strip().upper()
        if provider in (
            MeetingTranscription.Provider.GOOGLE_MEET,
            MeetingTranscription.Provider.ZOOM,
        ):
            qs = qs.filter(provider=provider)

        status_filter = (params.get('status') or '').strip().upper()
        valid_statuses = {choice[0] for choice in MeetingTranscription.Status.choices}
        if status_filter in valid_statuses:
            qs = qs.filter(status=status_filter)

        search = (params.get('search') or '').strip()
        if search:
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(transcript_text__icontains=search)
                | Q(meeting_url__icontains=search)
                | Q(provider_meeting_id__icontains=search)
            )

        date_from = parse_date((params.get('date_from') or '').strip())
        if date_from:
            qs = qs.filter(
                Q(scheduled_start__date__gte=date_from)
                | Q(scheduled_start__isnull=True, created_at__date__gte=date_from)
            )

        date_to = parse_date((params.get('date_to') or '').strip())
        if date_to:
            qs = qs.filter(
                Q(scheduled_start__date__lte=date_to)
                | Q(scheduled_start__isnull=True, created_at__date__lte=date_to)
            )

        ordering = (params.get('ordering') or '-scheduled_start').strip()
        if ordering in ('scheduled_start', 'created_at', 'oldest'):
            qs = qs.order_by('scheduled_start', 'created_at')
        else:
            qs = qs.order_by('-scheduled_start', '-created_at')

        return qs

    @action(detail=True, methods=['post'], url_path='refresh')
    def refresh(self, request, id=None):
        """
        Manually refresh/re-fetch a Zoom transcription from Zoom Cloud Recording API.
        For Google Meet (CBE) transcriptions, returns the current record state.
        """
        transcription = self.get_object()
        if transcription.provider == MeetingTranscription.Provider.ZOOM:
            updated = fetch_and_store_zoom_transcript(transcription, force=True)
            serializer = MeetingTranscriptionDetailSerializer(updated, context={'request': request})
            return Response(serializer.data, status=status.HTTP_200_OK)

        serializer = MeetingTranscriptionDetailSerializer(transcription, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=['post'],
        url_path='process-pending',
        permission_classes=[CanProcessPendingTranscriptions],
    )
    def process_pending(self, request):
        """Trigger pending transcription recovery (Manager / Superuser only)."""
        try:
            max_items = min(max(int(request.data.get('max_items', 50)), 1), 200)
        except (TypeError, ValueError):
            max_items = 50
        summary = process_pending_transcriptions(max_items=max_items)
        return Response(summary, status=status.HTTP_200_OK)


class ZoomWebhookView(APIView):
    """
    POST /api/transcriptions/webhooks/zoom/
    Handles Zoom Event Subscriptions with HMAC-SHA256 signature validation:
    - endpoint.url_validation (CRC challenge)
    - recording.completed / recording.transcript_completed
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw_body = request.body or b''
        try:
            payload = json.loads(raw_body.decode('utf-8')) if raw_body else {}
        except (ValueError, UnicodeDecodeError):
            return Response({'error': 'Invalid JSON payload.'}, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(payload, dict):
            return Response({'error': 'Invalid JSON payload.'}, status=status.HTTP_400_BAD_REQUEST)

        # Always verify Zoom signature headers (including for endpoint.url_validation)
        is_valid, err = verify_zoom_webhook_signature(request.headers, raw_body)
        if not is_valid:
            logger.warning('Zoom webhook signature verification failed: %s', err)
            return Response({'error': err}, status=status.HTTP_401_UNAUTHORIZED)

        status_code, body = handle_zoom_webhook_payload(payload)
        return Response(body, status=status_code)
