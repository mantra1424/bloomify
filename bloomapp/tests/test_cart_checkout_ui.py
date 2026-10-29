"""Phase 4 redesign: slide-in cart, 3-step checkout, payment and success pages."""

from datetime import time, timedelta

from django.urls import reverse
from django.utils import timezone

from bloomapp.models import CartItem, DeliverySlot, Order
from bloomapp.tests.test_checkout_and_payments import CHECKOUT, BaseShopTest

AJAX = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
COD = {'payment_mode': 'cod'}


def make_slot(days_ahead=1, start=time(9), end=time(11), **extra):
    return DeliverySlot.objects.create(
        date=timezone.localdate() + timedelta(days=days_ahead),
        slot_label='9 AM – 11 AM',
        slot_start=start,
        slot_end=end,
        **extra,
    )


class CartDrawerTests(BaseShopTest):
    def test_ajax_add_returns_drawer_html_and_count(self):
        res = self.client.post(reverse('add_to_cart', args=[self.cheap.pk]), {'quantity': 2}, **AJAX)
        data = res.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['cart_count'], 1)  # badge counts lines, not units
        self.assertIn('Mini', data['html'])
        self.assertIn(reverse('checkout'), data['html'])

    def test_ajax_add_when_all_stock_is_in_cart_is_a_conflict(self):
        CartItem.objects.create(user=self.user, product=self.cheap, quantity=5)
        res = self.client.post(reverse('add_to_cart', args=[self.cheap.pk]), **AJAX)
        self.assertEqual(res.status_code, 409)
        self.assertFalse(res.json()['ok'])

    def test_normal_add_still_redirects(self):
        res = self.client.post(reverse('add_to_cart', args=[self.cheap.pk]))
        self.assertEqual(res.status_code, 302)

    def test_cart_page_shows_free_delivery_meter(self):
        CartItem.objects.create(user=self.user, product=self.cheap, quantity=1)
        res = self.client.get(reverse('cart'))
        self.assertContains(res, 'more for free delivery')


class CheckoutPageTests(BaseShopTest):
    def test_checkout_page_gets_pincode_map_for_the_browser(self):
        CartItem.objects.create(user=self.user, product=self.cheap, quantity=1)
        res = self.client.get(reverse('checkout'))
        self.assertEqual(res.context['delivery_config']['pincode_areas']['388'], 'anand')
        self.assertContains(res, 'co-progress')

    def test_pincode_from_another_city_is_rejected(self):
        CartItem.objects.create(user=self.user, product=self.cheap, quantity=1)
        res = self.client.post(reverse('place_order'), {**CHECKOUT, **COD, 'pincode': '390001'}, follow=True)
        self.assertFalse(Order.objects.exists())
        self.assertContains(res, 'not Anand')

    def test_chosen_slot_is_booked(self):
        slot = make_slot()
        self.buy(self.cheap, slot_id=slot.id, **COD)
        slot.refresh_from_db()
        self.assertEqual(slot.booked_count, 1)
        self.assertEqual(Order.objects.get().delivery_slot, slot)


class SlotTimeTests(BaseShopTest):
    def test_slot_that_already_started_is_closed(self):
        now = timezone.localtime()
        past = make_slot(days_ahead=0, start=(now - timedelta(hours=1)).time(), end=now.time())
        self.assertTrue(past.has_started)
        self.assertFalse(past.is_bookable)
        self.assertTrue(make_slot(days_ahead=1).is_bookable)

    def test_slots_api_marks_started_slots_closed(self):
        yesterday_like = make_slot(days_ahead=0, start=time(0, 0), end=time(0, 1))
        res = self.client.get(reverse('get_slots'), {'date': yesterday_like.date.isoformat()})
        slot = next(s for s in res.json()['slots'] if s['id'] == yesterday_like.id)
        self.assertEqual((slot['available'], slot['closed']), (False, True))

    def test_started_slot_is_not_booked(self):
        slot = make_slot(days_ahead=0, start=time(0, 0), end=time(0, 1))
        self.buy(self.cheap, slot_id=slot.id, **COD)
        slot.refresh_from_db()
        self.assertEqual(slot.booked_count, 0)
        self.assertIsNone(Order.objects.get().delivery_slot)


class ConfirmationPageTests(BaseShopTest):
    def test_cod_success_page_says_pay_on_delivery(self):
        slot = make_slot()
        self.buy(self.cheap, slot_id=slot.id, **COD)
        order = Order.objects.get()
        res = self.client.get(reverse('order_success', args=[order.pk]))
        self.assertContains(res, 'To pay on delivery')
        self.assertContains(res, slot.slot_label)

    def test_payment_page_passes_options_as_json(self):
        res = self.buy(self.cheap, payment_mode='online')
        options = res.context['razorpay_options']
        self.assertEqual(options['amount'], int(Order.objects.get().total_amount * 100))
        self.assertEqual(options['prefill']['email'], 'buyer@example.com')
        self.assertContains(res, 'id="rzp-options"')
        self.assertEqual(options['currency'], 'INR')


class FormErrorMessageTests(BaseShopTest):
    def test_missing_field_error_names_the_field(self):
        CartItem.objects.create(user=self.user, product=self.cheap, quantity=1)
        res = self.client.post(reverse('place_order'), CHECKOUT, follow=True)
        self.assertEqual([str(m) for m in res.context['messages']], ['Payment mode is required.'])
