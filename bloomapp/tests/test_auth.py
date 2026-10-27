import pytest
from django.core import mail
from django.test import override_settings
from django.urls import reverse

from bloomapp.models import User

pytestmark = pytest.mark.django_db


def test_signup_creates_account_and_logs_in(client):
    response = client.post(
        reverse('signup'),
        {
            'full_name': 'Asha Patel',
            'email': 'asha@example.com',
            'phone': '9876543210',
            'password': 'Bl00m-garden!',
            'confirm_password': 'Bl00m-garden!',
        },
    )
    assert response.status_code == 302
    user = User.objects.get(email='asha@example.com')
    assert user.role == 'user'
    assert client.get(reverse('dashboard')).status_code == 200


def test_login_with_correct_password(client, customer):
    response = client.post(reverse('login'), {'email': 'BUYER@example.com', 'password': 'Str0ng-pass!'})
    assert response.status_code == 302
    assert response.wsgi_request.user == customer


def test_wrong_password_gives_generic_message(client, customer):
    response = client.post(reverse('login'), {'email': customer.email, 'password': 'nope'}, follow=True)
    assert not response.wsgi_request.user.is_authenticated
    assert 'Incorrect email or password.' in response.content.decode()


@pytest.mark.parametrize(
    ('next_url', 'expected'),
    [('/cart/', '/cart/'), ('https://evil.example.com/', '/'), ('//evil.example.com', '/')],
)
def test_login_only_redirects_within_the_site(client, customer, next_url, expected):
    response = client.post(f'{reverse("login")}?next={next_url}', {'email': customer.email, 'password': 'Str0ng-pass!'})
    assert response['Location'] == expected


def test_logout_needs_post(customer_client):
    assert customer_client.get(reverse('logout')).status_code == 405
    customer_client.post(reverse('logout'))
    assert customer_client.get(reverse('dashboard')).status_code == 302


def test_pages_that_need_login_redirect_to_login(client):
    response = client.get(reverse('cart'))
    assert response.status_code == 302
    assert response['Location'].startswith(reverse('login'))


@override_settings(AXES_ENABLED=True)
def test_account_locks_after_five_failed_logins(client, customer):
    for _ in range(5):
        client.post(reverse('login'), {'email': customer.email, 'password': 'wrong'})
    response = client.post(reverse('login'), {'email': customer.email, 'password': 'Str0ng-pass!'})
    assert response.status_code == 429
    assert not response.wsgi_request.user.is_authenticated


def test_password_reset_sends_a_working_link(client, customer):
    client.post(reverse('password_reset'), {'email': customer.email})
    assert len(mail.outbox) == 1
    link = next(line for line in mail.outbox[0].body.splitlines() if '/password-reset/' in line)
    path = link.split('testserver', 1)[1]

    response = client.get(path, follow=True)
    set_password_url = response.redirect_chain[-1][0]
    client.post(set_password_url, {'new_password1': 'New-bl00m-pass', 'new_password2': 'New-bl00m-pass'})
    customer.refresh_from_db()
    assert customer.check_password('New-bl00m-pass')


def test_password_reset_does_not_reveal_unknown_emails(client):
    response = client.post(reverse('password_reset'), {'email': 'nobody@example.com'})
    assert response['Location'] == reverse('password_reset_done')
    assert len(mail.outbox) == 0


def test_profile_password_change_keeps_user_logged_in(customer_client, customer):
    customer_client.post(
        reverse('dashboard'),
        {'action': 'update_profile', 'full_name': 'Test Buyer', 'phone': '', 'new_password': 'An0ther-pass!'},
    )
    customer.refresh_from_db()
    assert customer.check_password('An0ther-pass!')
    assert customer_client.get(reverse('dashboard')).status_code == 200
