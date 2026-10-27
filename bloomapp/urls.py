from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

urlpatterns = [
    # Home
    path('', views.home, name='home'),
    path('healthz/', views.healthz, name='healthz'),
    path('contact/', views.contact_view, name='contact'),
    path('faqs/', views.faq_view, name='faqs'),
    path('returns-policy/', views.returns_view, name='returns'),

    # Auth
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='bloomapp/auth/password_reset_form.html',
        email_template_name='bloomapp/emails/password_reset_email.txt',
        subject_template_name='bloomapp/emails/password_reset_subject.txt',
        success_url=reverse_lazy('password_reset_done'),
    ), name='password_reset'),
    path('password-reset/sent/', auth_views.PasswordResetDoneView.as_view(
        template_name='bloomapp/auth/password_reset_done.html',
    ), name='password_reset_done'),
    path('password-reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='bloomapp/auth/password_reset_confirm.html',
        success_url=reverse_lazy('password_reset_complete'),
    ), name='password_reset_confirm'),
    path('password-reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='bloomapp/auth/password_reset_complete.html',
    ), name='password_reset_complete'),

    # Products
    path('products/', views.products_list, name='products'),
    path('products/<int:pk>/', views.product_detail, name='product_detail'),
    path('products/<int:pk>/review/', views.submit_review, name='submit_review'),

    # Custom Bouquet
    path('custom-bouquet/', views.custom_bouquet_view, name='custom_bouquet'),

    # Cart
    path('cart/', views.cart_view, name='cart'),
    path('cart/add/<int:pk>/', views.add_to_cart, name='add_to_cart'),
    path('cart/update/', views.update_cart, name='update_cart'),
    path('cart/remove/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),

    # Checkout
    path('checkout/', views.checkout_view, name='checkout'),
    path('checkout/slots/', views.get_slots_ajax, name='get_slots'),
    path('checkout/delivery-charge/', views.get_delivery_charge_ajax, name='delivery_charge'),
    path('checkout/calculate-delivery/', views.calculate_delivery_api, name='calculate_delivery'),
    path('checkout/apply-coupon/', views.apply_coupon_ajax, name='apply_coupon'),

    # Payment & Orders
    path('payment/', views.payment_view, name='payment'),
    path('order/place/', views.place_order, name='place_order'),
    path('order/confirm-payment/', views.confirm_payment, name='confirm_payment'),
    path('payments/webhook/', views.razorpay_webhook, name='razorpay_webhook'),
    path('orders/<int:pk>/success/', views.order_success, name='order_success'),
    path('orders/<int:pk>/tracking/', views.order_tracking, name='order_tracking'),

    # User Dashboard
    path('dashboard/', views.user_dashboard, name='dashboard'),

    # Admin Panel
    path('admin-panel/login/', views.admin_login, name='admin_login'),
    path('admin-panel/logout/', views.admin_logout, name='admin_logout'),
    path('admin-panel/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-panel/api/analytics/', views.admin_analytics_api, name='admin_analytics_api'),
    path('admin-panel/products/', views.admin_products, name='admin_products'),
    path('admin-panel/products/add/', views.admin_product_add, name='admin_product_add'),
    path('admin-panel/products/<int:pk>/edit/', views.admin_product_edit, name='admin_product_edit'),
    path('admin-panel/products/<int:pk>/delete/', views.admin_product_delete, name='admin_product_delete'),
    path('admin-panel/orders/', views.admin_orders, name='admin_orders'),
    path('admin-panel/orders/<int:pk>/update/', views.admin_order_update, name='admin_order_update'),
    path('admin-panel/users/', views.admin_users, name='admin_users'),
    path('admin-panel/coupons/', views.admin_coupons, name='admin_coupons'),
    path('admin-panel/messages/', views.admin_messages, name='admin_messages'),
    path('admin-panel/sales-report/', views.admin_sales_report, name='admin_sales_report'),
    path('admin-panel/sales-report/download/', views.admin_sales_report_csv, name='admin_sales_report_csv'),
    path('admin-panel/sales-report/print/', views.admin_sales_report_print, name='admin_sales_report_print'),

    # Wishlist
    path('wishlist/', views.wishlist_view, name='wishlist'),
    path('wishlist/toggle/<int:pk>/', views.toggle_wishlist, name='toggle_wishlist'),

    # Newsletter
    path('newsletter/subscribe/', views.newsletter_subscribe, name='newsletter_subscribe'),

    # Search Autocomplete
    path('products/autocomplete/', views.search_autocomplete, name='search_autocomplete'),

    # Order Cancellation
    path('orders/<int:pk>/cancel/', views.cancel_order, name='cancel_order'),
]
