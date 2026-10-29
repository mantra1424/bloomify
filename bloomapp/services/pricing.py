"""Prices and charges. This is the single source of truth for serviceable cities."""

import re
from decimal import ROUND_HALF_UP, Decimal

from bloomapp.utils import parse_float

# key → display name, base delivery charge (₹) and estimated delivery time.
DELIVERY_CITIES = {
    'anand': {'name': 'Anand', 'charge': 20, 'eta': '2–4 hrs'},
    'vadodara': {'name': 'Vadodara', 'charge': 30, 'eta': '2–4 hrs'},
    'ahmedabad': {'name': 'Ahmedabad', 'charge': 40, 'eta': '3–5 hrs'},
    'surat': {'name': 'Surat', 'charge': 50, 'eta': '3–5 hrs'},
    'bharuch': {'name': 'Bharuch', 'charge': 25, 'eta': '2–4 hrs'},
    'nadiad': {'name': 'Nadiad', 'charge': 30, 'eta': '2–3 hrs'},
}

TIME_CHARGES = {'normal': 0, 'sameday': 50, 'midnight': 120}

# First three digits of the pincode areas we deliver to. These are postal areas,
# so they also cover some towns around each city.
PINCODE_AREAS = {
    '380': 'ahmedabad',
    '382': 'ahmedabad',
    '387': 'nadiad',
    '388': 'anand',
    '390': 'vadodara',
    '391': 'vadodara',
    '392': 'bharuch',
    '394': 'surat',
    '395': 'surat',
}

FREE_DELIVERY_ABOVE = 1000  # subtotal (₹) at which delivery is free
DELIVERY_DISCOUNT_ABOVE = 500  # subtotal (₹) at which ₹30 is taken off delivery
DELIVERY_DISCOUNT = 30

# Custom bouquet: base ₹150 + (₹20 + flower surcharge) per stem + wrapping + ₹30 for a message card.
BOUQUET_BASE_PRICE = 150
BOUQUET_PRICE_PER_STEM = 20
FLOWER_SURCHARGES = {'rose': 0, 'lily': 10, 'tulip': 15, 'sunflower': 5, 'orchid': 20}  # extra ₹ per stem
BOUQUET_MESSAGE_CARD_PRICE = 30
BOUQUET_MIN_STEMS = 1
BOUQUET_MAX_STEMS = 100
WRAPPING_COSTS = {'classic': 0, 'rustic': 50, 'luxury': 150, 'minimal': 30}


def city_key(city):
    return (city or '').strip().lower()


def is_serviceable(city):
    return city_key(city) in DELIVERY_CITIES


def serviceable_city_names():
    return [c['name'] for c in DELIVERY_CITIES.values()]


def city_for_pincode(pincode):
    """City key for a 6-digit pincode we deliver to, else None."""
    pincode = (pincode or '').strip()
    if not re.fullmatch(r'[1-9]\d{5}', pincode):
        return None
    return PINCODE_AREAS.get(pincode[:3])


def delivery_quote(pincode):
    """What a customer sees after entering a pincode: city, delivery time and lowest charge."""
    key = city_for_pincode(pincode)
    if key is None:
        return None
    city = DELIVERY_CITIES[key]
    return {
        'pincode': pincode.strip(),
        'city': city['name'],
        'eta': city['eta'],
        # Cheapest normal delivery: city charge + the shortest distance band.
        'charge_from': city['charge'] + distance_charge(0),
        'free_above': FREE_DELIVERY_ABOVE,
    }


def distance_charge(km):
    if km <= 5:
        return 30
    if km <= 10:
        return 60
    return 100


def calc_delivery(city, distance_km, delivery_type, subtotal):
    """Work out the delivery charge and how it was made up."""
    city_c = DELIVERY_CITIES.get(city_key(city), {}).get('charge', 0)
    km = parse_float(distance_km, 3.0, min_value=0, max_value=500)
    dist_c = distance_charge(km)
    time_c = TIME_CHARGES.get(delivery_type, 0)
    gross = city_c + dist_c + time_c
    discount = 0
    is_free = subtotal >= FREE_DELIVERY_ABOVE
    if is_free:
        discount, gross = gross, 0
    elif subtotal >= DELIVERY_DISCOUNT_ABOVE:
        discount = min(DELIVERY_DISCOUNT, gross)
        gross = max(0, gross - discount)
    return {
        'city_charge': city_c,
        'distance_charge': dist_c,
        'time_charge': time_c,
        'discount': discount,
        'delivery_charge': gross,
        'is_free': is_free,
    }


def coupon_discount(subtotal, coupon):
    """Discount in rupees for a valid coupon, rounded to paise."""
    amount = Decimal(str(subtotal)) * coupon.discount_percent / 100
    return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def custom_bouquet_price(stem_count, wrapping, has_message, flower='rose'):
    per_stem = BOUQUET_PRICE_PER_STEM + FLOWER_SURCHARGES[flower]
    price = BOUQUET_BASE_PRICE + stem_count * per_stem + WRAPPING_COSTS[wrapping]
    if has_message:
        price += BOUQUET_MESSAGE_CARD_PRICE
    return price


def bouquet_pricing_config():
    """Prices sent to the bouquet builder page so its preview matches what we charge."""
    return {
        'base': BOUQUET_BASE_PRICE,
        'per_stem': BOUQUET_PRICE_PER_STEM,
        'message_card': BOUQUET_MESSAGE_CARD_PRICE,
        'flower_surcharges': FLOWER_SURCHARGES,
        'wrapping': WRAPPING_COSTS,
    }
