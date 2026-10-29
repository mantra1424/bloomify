"""
Views, grouped by area. Everything is re-exported here so `bloomapp/urls.py`
can keep referring to `views.<name>`.
"""

from .accounts import login_view, logout_view, signup_view, user_dashboard
from .admin_panel import *  # noqa: F401,F403
from .cart import add_to_cart, cart_view, remove_from_cart, update_cart
from .catalog import (
    custom_bouquet_view,
    product_detail,
    products_list,
    search_autocomplete,
    submit_review,
    toggle_wishlist,
    wishlist_view,
)
from .checkout import (
    apply_coupon_ajax,
    calculate_delivery_api,
    check_pincode,
    checkout_view,
    get_delivery_charge_ajax,
    get_slots_ajax,
    place_order,
)
from .orders import cancel_order, order_success, order_tracking
from .pages import contact_view, faq_view, healthz, home, newsletter_subscribe, photo_credits_view, returns_view
from .payments import confirm_payment, payment_view, razorpay_webhook
