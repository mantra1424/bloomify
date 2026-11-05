"""Template helpers for the storefront: {% load bloom %}."""

from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import conditional_escape, format_html
from django.utils.safestring import mark_safe

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


@register.simple_tag(takes_context=True)
def logo(context, show_mark=True):
    """The shop's logo: the tulip mark and the name, with the ampersand set in italic."""
    brand = context.get('brand') or settings.SITE_BRAND
    # Each part is escaped before the italic ampersand is put back between them.
    name = mark_safe('<em>&amp;</em>'.join(conditional_escape(part) for part in brand.split('&')))  # noqa: S308
    mark = render_to_string('bloomapp/partials/logo_mark.svg') if show_mark else ''
    return format_html('{}<span class="logo-name">{}</span>', mark_safe(mark), name)  # noqa: S308
