import os
filepath = r'whatsapp\views.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

target = """        if contact_id:
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
        else:
            # Fallback for unmatched chats (chat_id provided, no contact_id)
            import uuid
            from .client import get_waha_client
            from .models import WhatsAppConversation, WhatsAppMessage
            try:
                client = get_waha_client()
                waha_res = client.send_text(session_name, raw_chat_id, message_body)
                
                # Save to database
                conv = WhatsAppConversation.objects.filter(chat_id=raw_chat_id).first()
                if not conv:
                    return Response({"detail": "Conversation not found."}, status=404)
                    
                msg = WhatsAppMessage.objects.create(
                    conversation=conv,
                    idempotency_key=str(uuid.uuid4()),
                    message_id=waha_res.get("id", ""),
                    body=message_body,
                    is_from_me=True,
                    status=WhatsAppMessage.Status.SENT,
                    performed_by=request.user
                )
                return Response(
                    WhatsAppMessageSerializer(msg).data,
                    status=status.HTTP_201_CREATED,
                )
            except Exception as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        
        # This throwaway try block prevents indentation errors for the catch blocks below
        try:
            pass

        except WhatsAppBlockedError as exc:
            return Response(
                {"detail": str(exc), "code": exc.code},
                status=status.HTTP_403_FORBIDDEN,
            )
        except WhatsAppAuthorizationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except WhatsAppError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)"""

replacement = """        if contact_id:
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
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            # Fallback for unmatched chats (chat_id provided, no contact_id)
            import uuid
            from .client import get_waha_client
            from .models import WhatsAppConversation, WhatsAppMessage
            try:
                client = get_waha_client()
                waha_res = client.send_text(session_name, raw_chat_id, message_body)
                
                # Save to database
                conv = WhatsAppConversation.objects.filter(chat_id=raw_chat_id).first()
                if not conv:
                    return Response({"detail": "Conversation not found."}, status=404)
                    
                msg = WhatsAppMessage.objects.create(
                    conversation=conv,
                    idempotency_key=str(uuid.uuid4()),
                    message_id=waha_res.get("id", ""),
                    body=message_body,
                    is_from_me=True,
                    status=WhatsAppMessage.Status.SENT,
                    performed_by=request.user
                )
                return Response(
                    WhatsAppMessageSerializer(msg).data,
                    status=status.HTTP_201_CREATED,
                )
            except Exception as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)"""

if target in content:
    content = content.replace(target, replacement)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Patched views.py successfully")
else:
    print("Target not found in views.py!")
