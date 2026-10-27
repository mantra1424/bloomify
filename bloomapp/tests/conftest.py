"""Shared pytest fixtures."""

from itertools import count
from unittest.mock import patch

import pytest

from bloomapp.models import Category, Product, User

_rzp_ids = count(1)


def fake_rzp_create(self, data=None, **kwargs):
    return {'id': f'order_TEST{next(_rzp_ids)}', 'amount': data['amount']}


@pytest.fixture(autouse=True)
def no_real_razorpay():
    """Never call Razorpay's servers from tests."""
    with patch('razorpay.resources.order.Order.create', fake_rzp_create):
        yield


@pytest.fixture
def customer(db):
    return User.objects.create_user(email='buyer@example.com', password='Str0ng-pass!', full_name='Test Buyer')


@pytest.fixture
def staff(db):
    return User.objects.create_user(email='staff@example.com', password='x', full_name='Staff', role='staff')


@pytest.fixture
def admin(db):
    return User.objects.create_user(email='admin@example.com', password='x', full_name='Admin', role='admin')


@pytest.fixture
def category(db):
    return Category.objects.create(name='Roses', slug='roses')


@pytest.fixture
def product(category):
    return Product.objects.create(name='Red Roses', category=category, original_price=800, price=700, stock_quantity=5)


@pytest.fixture
def customer_client(client, customer):
    client.force_login(customer)
    return client


@pytest.fixture
def staff_client(client, staff):
    client.force_login(staff)
    return client


@pytest.fixture
def admin_client_panel(client, admin):
    client.force_login(admin)
    return client


CHECKOUT = {
    'full_name': 'Test Buyer',
    'phone': '9876543210',
    'address': 'B-12, Near Station Rd.',
    'pincode': '388001',
    'city': 'Anand',
    'state': 'Gujarat',
    'email': 'buyer@example.com',
}
