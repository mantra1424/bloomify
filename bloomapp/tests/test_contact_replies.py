"""Staff answering contact messages from the admin panel."""

from unittest.mock import patch

import pytest
from django.urls import reverse

from bloomapp.models import ContactMessage

pytestmark = pytest.mark.django_db

URL = reverse('admin_messages')


@pytest.fixture
def msg():
    return ContactMessage.objects.create(
        name='Riya Shah', email='riya@example.com', subject='Delivery', message='Can you deliver at 7 & 8 pm?'
    )


def reply(client, msg, text='Hi Riya,\n\nYes, 7 pm works & we will call first.'):
    return client.post(URL, {'msg_id': msg.pk, 'action': 'reply', 'reply': text})


def test_staff_reply_emails_the_customer_and_is_recorded(staff_client, staff, msg, mailoutbox, settings):
    settings.SITE_BRAND = 'Petal & Stem'
    res = reply(staff_client, msg)
    assert res.status_code == 302 and res['Location'].endswith(f'?open={msg.pk}#msg-{msg.pk}')

    mail = mailoutbox[0]
    assert mail.to == ['riya@example.com']
    assert mail.subject == 'Re: Delivery – Petal & Stem'
    # Plain-text email: no HTML escaping, signed by the staff member, original quoted.
    assert '7 pm works & we will call first.' in mail.body
    assert 'Staff\nPetal & Stem' in mail.body
    assert 'Can you deliver at 7 & 8 pm?' in mail.body and '&amp;' not in mail.body

    msg.refresh_from_db()
    assert msg.is_replied and msg.is_read and msg.replied_by == staff
    assert msg.reply.startswith('Hi Riya,')


def test_replied_message_shows_the_reply_instead_of_the_form(staff_client, msg):
    reply(staff_client, msg)
    page = staff_client.get(URL + f'?open={msg.pk}').content.decode()
    assert '✓ Replied by Staff' in page
    assert 'name="reply"' not in page
    assert f'id="detail-{msg.pk}"' in page and 'msg-detail open' in page


def test_unanswered_message_offers_a_reply_box_greeting_by_first_name(staff_client, msg):
    page = staff_client.get(URL).content.decode()
    assert 'name="reply"' in page and 'Hi Riya,' in page
    assert '1 needs a reply' in page


def test_empty_reply_is_not_sent(staff_client, msg, mailoutbox):
    reply(staff_client, msg, text='   ')
    msg.refresh_from_db()
    assert not mailoutbox and not msg.is_replied


def test_message_is_only_answered_once(staff_client, msg, mailoutbox):
    reply(staff_client, msg)
    reply(staff_client, msg, text='A second answer')
    assert len(mailoutbox) == 1
    msg.refresh_from_db()
    assert 'second' not in msg.reply


def test_failed_email_keeps_the_message_unanswered(staff_client, msg):
    with patch('bloomapp.services.emails.send_mail', side_effect=OSError('smtp down')):
        res = reply(staff_client, msg)
    msg.refresh_from_db()
    assert not msg.is_replied
    assert 'could not be sent' in str(list(res.wsgi_request._messages)[0])


def test_customers_cannot_reply(customer_client, msg, mailoutbox):
    reply(customer_client, msg)
    msg.refresh_from_db()
    assert not msg.is_replied and not mailoutbox


def test_bad_message_id_is_not_found(staff_client):
    assert staff_client.post(URL, {'msg_id': 'abc', 'action': 'reply', 'reply': 'x'}).status_code == 404
