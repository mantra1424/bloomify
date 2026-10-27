from decimal import Decimal
from types import SimpleNamespace

import pytest

from bloomapp.services import pricing


@pytest.mark.parametrize(
    ('km', 'expected'),
    [(0, 30), (5, 30), (5.1, 60), (10, 60), (10.5, 100), (400, 100)],
)
def test_distance_charge_bands(km, expected):
    assert pricing.distance_charge(km) == expected


def test_delivery_adds_city_distance_and_time_charges():
    result = pricing.calc_delivery('Surat', 7, 'midnight', subtotal=200)
    assert result == {
        'city_charge': 50,
        'distance_charge': 60,
        'time_charge': 120,
        'discount': 0,
        'delivery_charge': 230,
        'is_free': False,
    }


def test_delivery_is_reduced_from_500_and_free_from_1000():
    assert pricing.calc_delivery('Anand', 3, 'normal', 499)['delivery_charge'] == 50
    assert pricing.calc_delivery('Anand', 3, 'normal', 500)['delivery_charge'] == 20
    free = pricing.calc_delivery('Anand', 3, 'normal', 1000)
    assert free['delivery_charge'] == 0
    assert free['is_free'] is True


def test_bad_distance_falls_back_to_default():
    assert pricing.calc_delivery('Anand', 'abc', 'normal', 0)['distance_charge'] == 30


def test_unknown_delivery_type_costs_nothing_extra():
    assert pricing.calc_delivery('Anand', 3, 'teleport', 0)['time_charge'] == 0


@pytest.mark.parametrize('city', ['Anand', 'anand', '  NADIAD ', 'Vadodara'])
def test_serviceable_cities(city):
    assert pricing.is_serviceable(city)


@pytest.mark.parametrize('city', ['Mumbai', '', None, 'Vapi'])
def test_unserviceable_cities(city):
    assert not pricing.is_serviceable(city)


def test_coupon_discount_rounds_to_paise():
    coupon = SimpleNamespace(discount_percent=15)
    assert pricing.coupon_discount(Decimal('699.99'), coupon) == Decimal('105.00')


@pytest.mark.parametrize(
    ('stems', 'wrapping', 'message', 'expected'),
    [(1, 'classic', False, 170), (12, 'rustic', False, 440), (12, 'luxury', True, 570)],
)
def test_custom_bouquet_price(stems, wrapping, message, expected):
    assert pricing.custom_bouquet_price(stems, wrapping, message) == expected
