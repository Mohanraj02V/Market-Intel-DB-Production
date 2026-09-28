with open('whatsapp/views.py', 'r') as f:
    content = f.read()

target = '''    def post(self, request):
        # Read raw body for HMAC verification.
        raw_body = request.body
        signature = request.headers.get("X-Whatsapp-Signature", "")
        remote_addr = _get_client_ip(request)'''

replacement = '''    def post(self, request):
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
                _f.write(_json.dumps(_payload, indent=2, ensure_ascii=False) + "\\n\\n---\\n\\n")
        except Exception as _e:
            logger.warning("WEBHOOK_DEBUG logging failed: %s", _e)'''

content = content.replace(target, replacement)
with open('whatsapp/views.py', 'w') as f:
    f.write(content)
print('Done')
