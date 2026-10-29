"""Template helpers for the storefront: {% load bloom %}."""

from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


@register.filter
def rupees(value):
    """₹1,299 for whole amounts, ₹1,299.50 otherwise. Empty for missing values."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return ''
    if amount == amount.to_integral_value():
        return f'₹{int(amount):,}'
    return f'₹{amount:,.2f}'


@register.filter
def sub(value, arg):
    """value − arg, for amounts: {{ free_delivery_above|sub:subtotal }}."""
    try:
        return Decimal(str(value)) - Decimal(str(arg))
    except (InvalidOperation, TypeError, ValueError):
        return ''


@register.inclusion_tag('bloomapp/partials/icon.html')
def icon(name, size=20, label=''):
    """Inline line icon: {% icon 'truck' 20 %}. Decorative unless a label is given."""
    return {'name': name, 'size': size, 'label': label}
