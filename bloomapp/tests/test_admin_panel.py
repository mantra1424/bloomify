import pytest
from django.urls import reverse

from bloomapp.models import Order, Payment, Product
from bloomapp.services import orders as order_service
from bloomapp.services.orders import CheckoutDetails

from .conftest import CHECKOUT

pytestmark = pytest.mark.django_db

ADMIN_ONLY = [
    'admin_users',
    'admin_coupons',
    'admin_sales_report',
    'admin_sales_report_csv',
    'admin_sales_report_print',
]
STAFF_PAGES = ['admin_dashboard', 'admin_orders', 'admin_products', 'admin_messages']


def make_order(user, product, qty=1, payment_mode='cod'):
    from bloomapp.models import CartItem

    item = CartItem.objects.create(user=user, product=product, quantity=qty)
    details = CheckoutDetails(**{**CHECKOUT, 'payment_mode': payment_mode})
    return order_service.place_order(user, [item], details)


@pytest.mark.parametrize('name', STAFF_PAGES + ADMIN_ONLY)
def test_customers_cannot_open_admin_pages(customer_client, name):
    response = customer_client.get(reverse(name))
    assert response.status_code == 302
    assert response['Location'] == reverse('admin_login')


@pytest.mark.parametrize('name', STAFF_PAGES)
def test_staff_can_open_operational_pages(staff_client, name):
    assert staff_client.get(reverse(name)).status_code == 200


@pytest.mark.parametrize('name', ADMIN_ONLY)
def test_staff_cannot_open_admin_only_pages(staff_client, name):
    response = staff_client.get(reverse(name))
    assert response.status_code == 302
    assert response['Location'] == reverse('admin_dashboard')


def test_staff_get_403_from_analytics_api(staff_client):
    assert staff_client.get(reverse('admin_analytics_api')).status_code == 403


def test_staff_cannot_change_products(staff_client, product):
    staff_client.post(reverse('admin_product_delete', args=[product.id]))
    staff_client.post(reverse('admin_product_edit', args=[product.id]), {'name': 'Hacked'})
    product.refresh_from_db()
    assert product.name == 'Red Roses'


@pytest.mark.parametrize('name', STAFF_PAGES + ADMIN_ONLY + ['admin_analytics_api'])
def test_admin_can_open_everything(admin_client_panel, name, product, customer):
    make_order(customer, product)
    assert admin_client_panel.get(reverse(name)).status_code == 200


def test_customer_account_cannot_log_into_admin_panel(client, customer):
    client.post(reverse('admin_login'), {'email': customer.email, 'password': 'Str0ng-pass!'})
    assert client.get(reverse('admin_dashboard')).status_code == 302


def test_admin_can_add_product_with_validation(admin_client_panel, category):
    data = {
        'name': 'Tulips',
        'category': category.id,
        'original_price': 500,
        'price': 450,
        'stock_quantity': 4,
        'status': 'available',
    }
    admin_client_panel.post(reverse('admin_product_add'), data)
    assert Product.objects.filter(name='Tulips').exists()
    admin_client_panel.post(reverse('admin_product_add'), {**data, 'name': 'Bad', 'price': -5})
    assert not Product.objects.filter(name='Bad').exists()


def test_admin_edit_keeps_fields_the_dialog_does_not_send(admin_client_panel, product):
    product.flowers = 'rose'
    product.occasion_tags = 'love'
    product.save()
    admin_client_panel.post(
        reverse('admin_product_edit', args=[product.id]),
        {
            'name': 'Renamed',
            'category': product.category_id,
            'original_price': 800,
            'price': 650,
            'stock_quantity': 9,
            'status': 'available',
        },
    )
    product.refresh_from_db()
    assert (product.name, product.price, product.flowers, product.occasion_tags) == ('Renamed', 650, 'rose', 'love')


def test_admin_cancelling_an_order_restores_stock(admin_client_panel, customer, product):
    order = make_order(customer, product, qty=2)
    product.refresh_from_db()
    assert product.stock_quantity == 3
    admin_client_panel.post(reverse('admin_order_update', args=[order.id]), {'status': 'cancelled'})
    product.refresh_from_db()
    order.refresh_from_db()
    assert order.status == 'cancelled'
    assert product.stock_quantity == 5


def test_admin_cannot_set_unknown_status(admin_client_panel, customer, product):
    order = make_order(customer, product)
    admin_client_panel.post(reverse('admin_order_update', args=[order.id]), {'status': 'stolen'})
    order.refresh_from_db()
    assert order.status == 'placed'


def test_cancelled_orders_do_not_count_as_revenue(admin_client_panel, customer, product):
    kept = make_order(customer, product)
    cancelled = make_order(customer, product)
    order_service.cancel_order(cancelled)
    response = admin_client_panel.get(reverse('admin_dashboard'))
    assert response.context['total_revenue'] == kept.total_amount
    report = admin_client_panel.get(reverse('admin_sales_report'))
    assert report.context['total_revenue'] == kept.total_amount
    assert report.context['total_orders'] == 1


def test_csv_export_neutralises_spreadsheet_formulas(admin_client_panel, customer, product):
    order = make_order(customer, product)
    Order.objects.filter(pk=order.pk).update(city='=HYPERLINK("http://evil")')
    body = admin_client_panel.get(reverse('admin_sales_report_csv')).content.decode()
    assert "'=HYPERLINK" in body


def test_cod_order_has_cod_pending_payment(customer, product):
    order = make_order(customer, product)
    assert Payment.objects.get(order=order).status == 'cod_pending'
