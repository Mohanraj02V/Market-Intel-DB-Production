from django.contrib import admin
from .models import WhatsAppSession
from .services import start_session
import logging

logger = logging.getLogger(__name__)

@admin.register(WhatsAppSession)
class WhatsAppSessionAdmin(admin.ModelAdmin):
    list_display = ('session_name', 'status', 'owner', 'is_active', 'created_at')
    list_filter = ('status', 'is_active')
    search_fields = ('session_name', 'owner__username')
    readonly_fields = ('status', 'phone_number', 'owner', 'started_at', 'stopped_at', 'last_used_at')

    def get_fields(self, request, obj=None):
        if obj is None:
            return ('session_name',)
        return ('session_name', 'is_active', 'status', 'phone_number', 'owner')

    def save_model(self, request, obj, form, change):
        is_new = not obj.pk
        super().save_model(request, obj, form, change)
        
        try:
            from .services import get_session_status
            from .client import WAHAServiceError
            status_data = get_session_status(obj.session_name)
            waha_status = status_data.get('waha_status', {})
            status_str = str(waha_status.get('status', '')).upper()
            
            STATUS_MAP = {
                "STARTING": WhatsAppSession.Status.STARTING,
                "SCAN_QR_CODE": WhatsAppSession.Status.QR_REQUIRED,
                "WORKING": WhatsAppSession.Status.READY,
                "FAILED": WhatsAppSession.Status.FAILED,
                "STOPPED": WhatsAppSession.Status.STOPPED,
                "DISCONNECTED": WhatsAppSession.Status.DISCONNECTED,
            }
            if status_str in STATUS_MAP:
                obj.status = STATUS_MAP[status_str]
                me_data = waha_status.get('me', {})
                if isinstance(me_data, dict):
                    phone = str(me_data.get('phone') or me_data.get('id', '').split('@')[0])
                    if phone:
                        obj.phone_number = phone
                obj.save(update_fields=["status", "phone_number"])
        except Exception as exc:
            logger.warning(f"Failed to sync WAHA status for {obj.session_name}: {exc}")
            if is_new:
                try:
                    start_session(performed_by=request.user, session_name=obj.session_name)
                    obj.status = WhatsAppSession.Status.STARTING
                    obj.save(update_fields=["status"])
                    logger.info(f"Started WAHA session {obj.session_name} from Django Admin.")
                except Exception as exc2:
                    logger.error(f"Failed to start WAHA session {obj.session_name}: {exc2}")

