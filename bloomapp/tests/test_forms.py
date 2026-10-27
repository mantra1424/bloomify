import pytest

from bloomapp.forms import CheckoutForm, CouponForm, ProductForm, SignupForm

from .conftest import CHECKOUT


def checkout(**changes):
    return CheckoutForm({**CHECKOUT, 'payment_mode': 'cod', **changes})


@pytest.mark.parametrize(
    'address',
    ['B-12, Near Station Rd.', 'Flat 4/2, Shiv Apartments', "St. Mary's Road #7 (Opp. Park)"],
)
def test_real_world_addresses_are_accepted(address):
    assert checkout(address=address).is_valid()


@pytest.mark.parametrize('address', ['<script>alert(1)</script>', 'Road; DROP TABLE'])
def test_addresses_with_unsafe_characters_are_rejected(address):
    assert not checkout(address=address).is_valid()


def test_city_is_normalised_to_its_display_name():
    form = checkout(city='  vadodara ')
    assert form.is_valid()
    assert form.cleaned_data['city'] == 'Vadodara'


def test_unserviceable_city_lists_the_cities_we_serve():
    form = checkout(city='Mumbai')
    assert not form.is_valid()
    assert 'Anand' in form.errors['city'][0]


@pytest.mark.parametrize(
    ('field', 'value'),
    [('phone', '12345'), ('pincode', '38800'), ('payment_mode', 'free'), ('full_name', 'R2D2')],
)
def test_checkout_rejects_bad_values(field, value):
    assert not checkout(**{field: value}).is_valid()


def test_checkout_defaults():
    form = checkout()
    assert form.is_valid()
    details = form.to_details()
    assert details.delivery_type == 'normal'
    assert details.distance_km == 3.0
    assert details.slot_id is None


@pytest.mark.django_db
class TestSignupForm:
    data = {
        'full_name': 'New Person',
        'email': 'New@Example.com',
        'phone': '9876543210',
        'password': 'Bl00m-garden!',
        'confirm_password': 'Bl00m-garden!',
    }

    def test_valid_signup_creates_hashed_user(self):
        form = SignupForm(self.data)
        assert form.is_valid(), form.errors
        user = form.save()
        assert user.email == 'new@example.com'
        assert user.check_password('Bl00m-garden!')
        assert user.password != 'Bl00m-garden!'

    def test_password_mismatch(self):
        assert not SignupForm({**self.data, 'confirm_password': 'other'}).is_valid()

    @pytest.mark.parametrize('weak', ['short1', '12345678', 'password'])
    def test_weak_passwords_are_rejected(self, weak):
        assert not SignupForm({**self.data, 'password': weak, 'confirm_password': weak}).is_valid()

    def test_duplicate_email(self, customer):
        form = SignupForm({**self.data, 'email': customer.email.upper()})
        assert not form.is_valid()
        assert 'already registered' in form.errors['email'][0]


@pytest.mark.django_db
def test_product_form_rejects_price_above_original(category):
    form = ProductForm(
        {
            'name': 'X',
            'category': category.id,
            'original_price': 100,
            'price': 200,
            'stock_quantity': 1,
            'status': 'available',
        }
    )
    assert not form.is_valid()
    assert 'original_price' in form.errors


@pytest.mark.django_db
@pytest.mark.parametrize(('percent', 'ok'), [(0, False), (10, True), (95, False)])
def test_coupon_discount_limits(percent, ok):
    form = CouponForm({'code': 'save', 'discount_percent': percent, 'max_uses': 5, 'expiry': '2030-01-01'})
    assert form.is_valid() is ok
