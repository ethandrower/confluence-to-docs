from django.urls import re_path

from portal import consumers

websocket_urlpatterns = [
    re_path(r'^ws/tickets/(?P<number>\d+)/$', consumers.TicketConsumer.as_asgi()),
    re_path(r'^ws/admin/tickets/$', consumers.AdminInboxConsumer.as_asgi()),
    re_path(r'^ws/customer/tickets/$', consumers.CustomerListConsumer.as_asgi()),
]
