from rest_framework import serializers

from .models import MeetingTranscription


class MeetingTranscriptionListSerializer(serializers.ModelSerializer):
    owner_name = serializers.SerializerMethodField()
    owner_email = serializers.SerializerMethodField()
    provider_label = serializers.CharField(source='get_provider_display', read_only=True)
    source_label = serializers.CharField(source='get_source_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    duration_seconds = serializers.IntegerField(read_only=True)
    has_transcript = serializers.SerializerMethodField()
    segment_count = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()

    class Meta:
        model = MeetingTranscription
        fields = [
            'id',
            'user',
            'owner_name',
            'owner_email',
            'provider',
            'provider_label',
            'source',
            'source_label',
            'title',
            'meeting_url',
            'provider_meeting_id',
            'calendar_event_id',
            'meeting',
            'scheduled_start',
            'scheduled_end',
            'ended_at',
            'duration_seconds',
            'status',
            'status_label',
            'status_message',
            'completed_at',
            'has_transcript',
            'segment_count',
            'participant_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields

    def get_owner_name(self, obj):
        full = f"{obj.user.first_name} {obj.user.last_name}".strip()
        return full or obj.user.username

    def get_owner_email(self, obj):
        return obj.user.email or ''

    def get_has_transcript(self, obj):
        return bool((obj.transcript_text or '').strip())

    def get_segment_count(self, obj):
        segs = obj.speaker_segments or obj.transcript_segments or []
        return len(segs) if isinstance(segs, list) else 0

    def get_participant_count(self, obj):
        parts = obj.participants or []
        return len(parts) if isinstance(parts, list) else 0


class MeetingTranscriptionDetailSerializer(MeetingTranscriptionListSerializer):
    safe_metadata = serializers.SerializerMethodField()

    class Meta(MeetingTranscriptionListSerializer.Meta):
        fields = MeetingTranscriptionListSerializer.Meta.fields + [
            'provider_recording_id',
            'transcript_text',
            'transcript_segments',
            'speaker_segments',
            'participants',
            'safe_metadata',
        ]
        read_only_fields = fields

    def get_safe_metadata(self, obj):
        """Return non-sensitive metadata only; never expose tokens or private download URLs."""
        meta = obj.source_metadata if isinstance(obj.source_metadata, dict) else {}
        blocked_keys = {'download_url', 'access_token', 'refresh_token', 'authorization', 'token', 'secret'}
        return {
            k: v for k, v in meta.items()
            if str(k).lower() not in blocked_keys and 'token' not in str(k).lower() and 'secret' not in str(k).lower()
        }
