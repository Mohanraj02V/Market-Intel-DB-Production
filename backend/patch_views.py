import os

def patch_views():
    filepath = r'whatsapp\views.py'
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    target = """        data = serializer.validated_data
        contact_id = data["prospect_contact_id"]
        message_body = data["message_body"]
        session_name = data.get("session_name", "default")

        # Resolve the ProspectContact and enforce authorization.
        try:
            contact = ProspectContact.objects.select_related("prospect").get(pk=contact_id)
        except ProspectContact.DoesNotExist:
            return Response({"detail": "Key person not found."}, status=status.HTTP_404_NOT_FOUND)

        # Authorization: LQ users can only message contacts they are authorized for.
        # (The existing Market Intel permission model already controls which prospects
        # LQ users can access. We do not re-implement that here — we rely on the
        # existing ProspectContact queryset being properly scoped in the request.)
        # TODO: Enhance with company-level check when Company FK is added to UserProfile.

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
            )"""
            
    replacement = """        data = serializer.validated_data
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
            pass"""
            
    content = content.replace(target, replacement)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

patch_views()
print("Patched views.py")
