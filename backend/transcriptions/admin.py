from django.contrib import admin

from .models import MeetingTranscription


@admin.register(MeetingTranscription)
class MeetingTranscriptionAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'provider',
        'source',
        'user',
        'status',
        'scheduled_start',
        'completed_at',
    )
    list_filter = ('provider', 'source', 'status')
    search_fields = ('title', 'provider_meeting_id', 'calendar_event_id', 'user__username', 'user__email')
    readonly_fields = ('id', 'dedup_key', 'created_at', 'updated_at')
