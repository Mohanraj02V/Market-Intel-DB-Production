with open('whatsapp/urls.py', 'r') as f:
    content = f.read()

# Add the import
old_import = '''from .views import (
    WhatsAppAuditLogView,
    WhatsAppConfigView,
    WhatsAppConversationMessagesView,
    WhatsAppConversationSyncView,
    WhatsAppConversationsView,
    WhatsAppHealthView,
    WhatsAppOptOutsView,
    WhatsAppQRView,
    WhatsAppResetSafetyStopView,
    WhatsAppSafetyEventsView,
    WhatsAppSendMessageView,
    WhatsAppSessionLogoutView,
    WhatsAppSessionStartView,
    WhatsAppSessionStopView,
    WhatsAppSetOutboundView,
    WhatsAppStatusView,
    WhatsAppWebhookView,
)'''

new_import = '''from .views import (
    WhatsAppAuditLogView,
    WhatsAppConfigView,
    WhatsAppConversationMessagesView,
    WhatsAppConversationSyncView,
    WhatsAppConversationsView,
    WhatsAppHealthView,
    WhatsAppMediaProxyView,
    WhatsAppOptOutsView,
    WhatsAppQRView,
    WhatsAppResetSafetyStopView,
    WhatsAppSafetyEventsView,
    WhatsAppSendMessageView,
    WhatsAppSessionLogoutView,
    WhatsAppSessionStartView,
    WhatsAppSessionStopView,
    WhatsAppSetOutboundView,
    WhatsAppStatusView,
    WhatsAppWebhookView,
)'''

content = content.replace(old_import, new_import)

# Add the URL pattern
old_health = '    path("health/", WhatsAppHealthView.as_view(), name="whatsapp-health"),'
new_health = '''    path("health/", WhatsAppHealthView.as_view(), name="whatsapp-health"),

    # -- Media proxy (authenticated, proxies WAHA file URLs) ------------------
    path("media-proxy/", WhatsAppMediaProxyView.as_view(), name="whatsapp-media-proxy"),'''

content = content.replace(old_health, new_health)

with open('whatsapp/urls.py', 'w') as f:
    f.write(content)
print('Done!')
