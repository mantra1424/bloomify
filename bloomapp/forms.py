"""
Forms that validate everything users send us. Field names match the existing
templates' <input name="..."> attributes, so templates post to them unchanged.
"""
from django import forms
from django.contrib.auth import password_validation
from django.core.validators import RegexValidator

from .models import (
    FLOWER_CHOICES, PAYMENT_MODE, ContactMessage, Coupon, Product, SavedAddress, User,
)
from .services import pricing
from .services.orders import CheckoutDetails

name_validator = RegexValidator(r"^[A-Za-z][A-Za-z .'-]*$", 'Enter a valid name (letters and spaces only).')
phone_validator = RegexValidator(r'^[0-9]{10}$', 'Phone must be exactly 10 digits.')
pincode_validator = RegexValidator(r'^[0-9]{6}$', 'Pincode must be exactly 6 digits.')
# Real addresses use commas, slashes, hyphens, dots, '#', brackets and apostrophes.
address_validator = RegexValidator(
    r"^[A-Za-z0-9\s,./#'()&:-]+$",
    'Address can use letters, numbers, spaces and , . / - # \' ( ) & :',
)


def first_error(form):
    """The first error message on a form, for showing as a flash message."""
    for errors in form.errors.values():
        if errors:
            return errors[0]
    return 'Please check the form and try again.'


# ── Accounts ─────────────────────────────────────────────────────────────────
class SignupForm(forms.Form):
    full_name = forms.CharField(max_length=100, validators=[name_validator])
    email = forms.EmailField()
    phone = forms.CharField(max_length=15, required=False, validators=[phone_validator])
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Email already registered. Please login.')
        return email

    def clean(self):
        data = super().clean()
        if data.get('password') and data.get('password') != data.get('confirm_password'):
            raise forms.ValidationError('Passwords do not match.')
        if data.get('password'):
            candidate = User(email=data.get('email', ''), full_name=data.get('full_name', ''))
            password_validation.validate_password(data['password'], user=candidate)
        return data

    def save(self):
        return User.objects.create_user(
            email=self.cleaned_data['email'],
            password=self.cleaned_data['password'],
            full_name=self.cleaned_data['full_name'].strip(),
            phone=self.cleaned_data.get('phone', ''),
        )


class ProfileForm(forms.Form):
    full_name = forms.CharField(max_length=100, validators=[name_validator])
    phone = forms.CharField(max_length=15, required=False, validators=[phone_validator])
    new_password = forms.CharField(required=False, widget=forms.PasswordInput)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_new_password(self):
        password = self.cleaned_data.get('new_password')
        if password:
            password_validation.validate_password(password, user=self.user)
        return password

    def save(self):
        self.user.full_name = self.cleaned_data['full_name'].strip()
        self.user.phone = self.cleaned_data.get('phone', '')
        if self.cleaned_data.get('new_password'):
            self.user.set_password(self.cleaned_data['new_password'])
        self.user.save()
        return self.user


class AddressForm(forms.Form):
    label = forms.CharField(max_length=50, required=False)
    addr_name = forms.CharField(max_length=100, validators=[name_validator])
    addr_phone = forms.CharField(max_length=15, validators=[phone_validator])
    addr_street = forms.CharField(max_length=300, validators=[address_validator])
    addr_city = forms.CharField(max_length=100)
    addr_state = forms.CharField(max_length=100, required=False)
    addr_pincode = forms.CharField(max_length=10, validators=[pincode_validator])

    def save(self, user):
        d = self.cleaned_data
        return SavedAddress.objects.create(
            user=user, label=d.get('label') or 'Home', full_name=d['addr_name'],
            phone=d['addr_phone'], address=d['addr_street'], city=d['addr_city'],
            state=d.get('addr_state', ''), pincode=d['addr_pincode'],
        )


# ── Shop ─────────────────────────────────────────────────────────────────────
class CheckoutForm(forms.Form):
    full_name = forms.CharField(max_length=100, validators=[name_validator])
    email = forms.EmailField()
    phone = forms.CharField(validators=[phone_validator])
    address = forms.CharField(max_length=300, validators=[address_validator])
    city = forms.CharField(max_length=100)
    state = forms.CharField(max_length=100, required=False)
    pincode = forms.CharField(validators=[pincode_validator])
    payment_mode = forms.ChoiceField(choices=PAYMENT_MODE)
    delivery_type = forms.ChoiceField(choices=[(k, k) for k in pricing.TIME_CHARGES], required=False)
    distance_km = forms.FloatField(required=False, min_value=0, max_value=500)
    coupon_code = forms.CharField(max_length=30, required=False)
    slot_id = forms.IntegerField(required=False)
    special_note = forms.CharField(max_length=500, required=False)

    def clean_city(self):
        city = self.cleaned_data['city'].strip()
        if not pricing.is_serviceable(city):
            cities = ', '.join(pricing.serviceable_city_names())
            raise forms.ValidationError(f'Sorry, we don\'t deliver to "{city}" yet. We serve {cities}.')
        return pricing.DELIVERY_CITIES[pricing.city_key(city)]['name']

    def to_details(self):
        d = self.cleaned_data
        return CheckoutDetails(
            full_name=d['full_name'].strip(), email=d['email'], phone=d['phone'],
            address=d['address'].strip(), city=d['city'], state=d.get('state') or '',
            pincode=d['pincode'], payment_mode=d['payment_mode'],
            delivery_type=d.get('delivery_type') or 'normal',
            distance_km=d.get('distance_km') if d.get('distance_km') is not None else 3.0,
            coupon_code=d.get('coupon_code') or '', slot_id=d.get('slot_id'),
            special_note=d.get('special_note') or '',
        )


class CustomBouquetForm(forms.Form):
    flowers = forms.ChoiceField(choices=FLOWER_CHOICES)
    flower_count = forms.IntegerField(min_value=pricing.BOUQUET_MIN_STEMS, max_value=pricing.BOUQUET_MAX_STEMS)
    wrapping = forms.ChoiceField(choices=[(k, k) for k in pricing.WRAPPING_COSTS])
    message_card = forms.CharField(max_length=300, required=False)

    def price(self):
        d = self.cleaned_data
        return pricing.custom_bouquet_price(d['flower_count'], d['wrapping'], bool(d.get('message_card', '').strip()))


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'phone', 'subject', 'message']


# ── Admin panel ──────────────────────────────────────────────────────────────
class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'category', 'extra_categories', 'description', 'original_price', 'price',
            'stock_quantity', 'flowers', 'occasion_tags', 'is_featured', 'status',
            'image_main', 'image_2', 'image_3',
        ]

    def clean(self):
        data = super().clean()
        price, original = data.get('price'), data.get('original_price')
        if price is not None and price < 0:
            self.add_error('price', 'Price cannot be negative.')
        if price is not None and original is not None and original < price:
            self.add_error('original_price', 'Original price must be at least the selling price.')
        if data.get('stock_quantity') is not None and data['stock_quantity'] < 0:
            self.add_error('stock_quantity', 'Stock cannot be negative.')
        return data


class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = ['code', 'discount_percent', 'max_uses', 'expiry']

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()

    def clean_discount_percent(self):
        value = self.cleaned_data['discount_percent']
        if not 1 <= value <= 90:
            raise forms.ValidationError('Discount must be between 1% and 90%.')
        return value

    def clean_max_uses(self):
        value = self.cleaned_data['max_uses']
        if value < 1:
            raise forms.ValidationError('Max uses must be at least 1.')
        return value
