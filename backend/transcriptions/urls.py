from django.urls import include, path
from rest_framework.routers import DefaultRouter

from transcriptions.views import MeetingTranscriptionViewSet, ZoomWebhookView

router = DefaultRouter()
router.register(r'', MeetingTranscriptionViewSet, basename='meeting-transcription')

urlpatterns = [
    path('webhooks/zoom/', ZoomWebhookView.as_view(), name='zoom-transcription-webhook'),
    path('', include(router.urls)),
]
