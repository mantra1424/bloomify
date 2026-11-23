"""
Background work. Each task takes plain IDs (they are stored in a queue as JSON)
and is safe to run twice: a retry must never confuse the customer.
"""

from django.tasks import task

from bloomapp.models import Order
from bloomapp.services import emails


@task
def send_order_confirmation(order_id):
    """Email the order confirmation. Queued once the order (or its payment) is saved."""
    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        return 'missing'
    emails.send_order_confirmation_email(order)
    return 'sent'
