from .auth import admin_login, admin_logout
from .catalog import (
    admin_coupons,
    admin_product_add,
    admin_product_delete,
    admin_product_edit,
    admin_products,
)
from .dashboard import admin_analytics_api, admin_dashboard, admin_messages, admin_users
from .orders import admin_order_update, admin_orders
from .reports import admin_sales_report, admin_sales_report_csv, admin_sales_report_print

__all__ = [
    'admin_login',
    'admin_logout',
    'admin_dashboard',
    'admin_analytics_api',
    'admin_messages',
    'admin_users',
    'admin_products',
    'admin_product_add',
    'admin_product_edit',
    'admin_product_delete',
    'admin_coupons',
    'admin_orders',
    'admin_order_update',
    'admin_sales_report',
    'admin_sales_report_csv',
    'admin_sales_report_print',
]
