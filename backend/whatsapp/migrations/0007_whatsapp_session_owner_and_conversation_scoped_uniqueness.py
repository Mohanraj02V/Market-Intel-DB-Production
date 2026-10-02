"""
whatsapp/migrations/0007_whatsapp_session_owner_and_conversation_scoped_uniqueness.py

Migration:
  1. Add `owner` FK to WhatsAppSession.
  2. Add `is_active` and `last_used_at` to WhatsAppSession.
  3. Remove global unique constraint on WhatsAppConversation.chat_id.
  4. Add unique_together(session, chat_id) on WhatsAppConversation.
  5. Add soft-delete fields to WhatsAppConversation.
  6. Add soft-delete fields to WhatsAppMessage.
  7. Add SESSION_REGISTERED, SESSION_SELECTED, MESSAGE_DELETED, CONVERSATION_DELETED,
     AUTH_LOGOUT to WhatsAppAuditLog.Action choices.

Data safety:
  - Existing WhatsAppSession records without an owner remain with owner=NULL.
  - Existing WhatsAppConversation records: the old global unique constraint is
    removed and replaced with per-session uniqueness.
  - If any duplicate (session, chat_id) pairs exist they would violate the new
    constraint; but because existing conversations already had a globally unique
    chat_id the new constraint is automatically satisfied for existing data.
  - No data is deleted.
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("whatsapp", "0006_add_media_url_field"),
    ]

    operations = [
        # ------------------------------------------------------------------
        # 1. Add owner FK to WhatsAppSession
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="whatsappsession",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                help_text="The Market Intel user who owns and registered this WhatsApp session.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="whatsapp_sessions",
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # ------------------------------------------------------------------
        # 2. Add is_active to WhatsAppSession
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="whatsappsession",
            name="is_active",
            field=models.BooleanField(
                default=True,
                help_text="Whether this is one of the user's active sessions (not deleted/archived).",
            ),
        ),

        # ------------------------------------------------------------------
        # 3. Add last_used_at to WhatsAppSession
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="whatsappsession",
            name="last_used_at",
            field=models.DateTimeField(blank=True, null=True),
        ),

        # ------------------------------------------------------------------
        # 4. Remove old session_name default="default" from WhatsAppSession
        #    (just alter the field to remove default)
        # ------------------------------------------------------------------
        migrations.AlterField(
            model_name="whatsappsession",
            name="session_name",
            field=models.CharField(
                help_text="WAHA session name (matches WAHA session ID). Globally unique.",
                max_length=100,
                unique=True,
            ),
        ),

        # ------------------------------------------------------------------
        # 5. Add indexes on WhatsAppSession
        # ------------------------------------------------------------------
        migrations.AddIndex(
            model_name="whatsappsession",
            index=models.Index(fields=["owner", "is_active"], name="whatsapp_se_owner_is_active_idx"),
        ),
        migrations.AddIndex(
            model_name="whatsappsession",
            index=models.Index(fields=["session_name"], name="whatsapp_se_session_name_idx"),
        ),

        # ------------------------------------------------------------------
        # 6. Remove global unique constraint on WhatsAppConversation.chat_id
        # ------------------------------------------------------------------
        migrations.AlterField(
            model_name="whatsappconversation",
            name="chat_id",
            field=models.CharField(
                help_text="WhatsApp chat ID in format: <digits>@c.us",
                max_length=100,
            ),
        ),

        # ------------------------------------------------------------------
        # 7. Add unique_together(session, chat_id) on WhatsAppConversation
        # ------------------------------------------------------------------
        migrations.AlterUniqueTogether(
            name="whatsappconversation",
            unique_together={("session", "chat_id")},
        ),

        # ------------------------------------------------------------------
        # 8. Add soft-delete fields to WhatsAppConversation
        #    (index on session+is_deleted must come AFTER the field is added)
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="whatsappconversation",
            name="is_deleted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="whatsappconversation",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="whatsappconversation",
            name="deleted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="whatsapp_deleted_conversations",
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # ------------------------------------------------------------------
        # 9. Add index on WhatsAppConversation for session + is_deleted
        #    (AFTER is_deleted field is added above)
        # ------------------------------------------------------------------
        migrations.AddIndex(
            model_name="whatsappconversation",
            index=models.Index(fields=["session", "is_deleted"], name="whatsapp_co_session_deleted_idx"),
        ),

        # ------------------------------------------------------------------
        # 10. Add soft-delete fields to WhatsAppMessage
        #     (index must come AFTER the field is added)
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="whatsappmessage",
            name="is_deleted",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="whatsappmessage",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="whatsappmessage",
            name="deleted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="whatsapp_deleted_messages",
                to=settings.AUTH_USER_MODEL,
            ),
        ),

        # ------------------------------------------------------------------
        # 11. Add index on WhatsAppMessage for conversation + is_deleted + created_at
        #     (AFTER is_deleted field is added above)
        # ------------------------------------------------------------------
        migrations.AddIndex(
            model_name="whatsappmessage",
            index=models.Index(
                fields=["conversation", "is_deleted", "created_at"],
                name="whatsapp_ms_conv_deleted_created_idx",
            ),
        ),

        # ------------------------------------------------------------------
        # 12. Update WhatsAppAuditLog.action choices to include new actions
        #     (choices are metadata only; no schema change needed for CharField)
        # ------------------------------------------------------------------
        migrations.AlterField(
            model_name="whatsappauditlog",
            name="action",
            field=models.CharField(
                choices=[
                    ("SESSION_STARTED", "Session Started"),
                    ("SESSION_STOPPED", "Session Stopped"),
                    ("SESSION_REGISTERED", "Session Registered"),
                    ("SESSION_SELECTED", "Session Selected"),
                    ("QR_REQUESTED", "QR Requested"),
                    ("QR_SCANNED", "QR Scanned"),
                    ("SESSION_CONNECTED", "Session Connected"),
                    ("SESSION_DISCONNECTED", "Session Disconnected"),
                    ("MESSAGE_SENT", "Message Sent"),
                    ("MESSAGE_RECEIVED", "Message Received"),
                    ("MESSAGE_FAILED", "Message Failed"),
                    ("MESSAGE_DELETED", "Message Deleted"),
                    ("CONVERSATION_DELETED", "Conversation Deleted"),
                    ("SEND_BLOCKED", "Send Blocked"),
                    ("OPT_OUT_REGISTERED", "Opt-Out Registered"),
                    ("OPT_OUT_REVERSED", "Opt-Out Reversed"),
                    ("SAFETY_STOP", "Safety Stop"),
                    ("ADMIN_RESUMED", "Admin Resumed"),
                    ("CONFIG_CHANGED", "Config Changed"),
                    ("AUTH_LOGOUT", "Auth Logout"),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
    ]
