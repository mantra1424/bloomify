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
    ('stems', 'wrapping', 'message', 'flower', 'expected'),
    [
        (1, 'classic', False, 'rose', 170),  # 150 + 1×20
        (12, 'rustic', False, 'rose', 440),  # 150 + 12×20 + 50
        (12, 'luxury', True, 'rose', 570),  # 150 + 12×20 + 150 + 30
        (12, 'classic', False, 'lily', 510),  # 150 + 12×(20+10)
        (12, 'classic', False, 'tulip', 570),  # 150 + 12×(20+15)
        (12, 'classic', False, 'sunflower', 450),  # 150 + 12×(20+5)
        (10, 'minimal', True, 'orchid', 610),  # 150 + 10×(20+20) + 30 + 30
    ],
)
def test_custom_bouquet_price(stems, wrapping, message, flower, expected):
    assert pricing.custom_bouquet_price(stems, wrapping, message, flower=flower) == expected


def test_every_flower_choice_has_a_surcharge():
    from bloomapp.models import FLOWER_CHOICES

    assert set(pricing.FLOWER_SURCHARGES) == {key for key, _ in FLOWER_CHOICES}


@pytest.mark.parametrize(
    ('pincode', 'city'),
    [('388001', 'anand'), ('390007', 'vadodara'), ('380015', 'ahmedabad'), ('395003', 'surat'), (' 387001 ', 'nadiad')],
)
def test_city_for_pincode(pincode, city):
    assert pricing.city_for_pincode(pincode) == city


@pytest.mark.parametrize('pincode', ['400001', '38800', '3880011', '088001', 'abcdef', '', None])
def test_unknown_or_invalid_pincodes(pincode):
    assert pricing.city_for_pincode(pincode) is None


def test_delivery_quote_shows_lowest_normal_charge():
    quote = pricing.delivery_quote('388001')
    assert quote == {
        'pincode': '388001',
        'city': 'Anand',
        'eta': '2–4 hrs',
        'charge_from': 50,  # ₹20 city + ₹30 for the shortest distance
        'free_above': 1000,
    }
    assert quote['charge_from'] == pricing.calc_delivery('Anand', 0, 'normal', 0)['delivery_charge']
