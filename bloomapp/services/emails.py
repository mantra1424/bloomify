"""Customer emails. Sending is best-effort: a mail failure never breaks an order."""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_order_confirmation_email(order):
    items = list(order.items.select_related('product', 'custom_bouquet'))
    context = {'order': order, 'items': items}
    try:
        send_mail(
            subject=f'🌸 Order #{order.id} Confirmed – Bloomify',
            message=render_to_string('bloomapp/emails/order_confirmation.txt', context),
            html_message=render_to_string('bloomapp/emails/order_confirmation.html', context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.email],
        )
    except Exception:
        logger.exception('Could not send confirmation email for order %s', order.id)
