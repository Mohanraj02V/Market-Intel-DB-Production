with open('whatsapp/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_try = '''        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                waha_data = _json.loads(resp.read().decode("utf-8"))
                return Response({"status": "sent", "waha_response": waha_data}, status=200)
        except Exception as e:
            logger.error("Failed to send media via WAHA: %s", e)
            return Response({"detail": f"Failed to send media: {e}"}, status=502)'''

new_try = '''        try:
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
                )
                
                # Update conversation metadata
                conversation.last_message_at = timezone.now()
                conversation.last_message_preview = caption or f'[Media: {uploaded_file.name}]'
                conversation.last_message_from_me = True
                conversation.save(update_fields=['last_message_at', 'last_message_preview', 'last_message_from_me'])
        except Exception as e:
            logger.error("Failed to save media message to DB: %s", e)

        return Response({"status": "sent", "waha_response": waha_data}, status=200)'''

content = content.replace(old_try, new_try)
print('Backend fixed:', 'Save the outbound media message' in content)

with open('whatsapp/views.py', 'w', encoding='utf-8') as f:
    f.write(content)
