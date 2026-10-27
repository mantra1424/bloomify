import hashlib
import hmac
from datetime import timedelta
from itertools import count
from unittest.mock import patch

from django.contrib.auth.hashers import make_password
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    CartItem, Category, Coupon, CustomBouquet, DeliverySlot, Order, Payment,
    Product, User,
)
from .views import release_expired_online_orders

TEST_SECRET = 'test-razorpay-secret'
_rzp_ids = count(1)


def fake_rzp_create(self, data=None, **kwargs):
    return {'id': f'order_TEST{next(_rzp_ids)}', 'amount': data['amount']}


def sign(rzp_order_id, payment_id):
    msg = f'{rzp_order_id}|{payment_id}'.encode()
    return hmac.new(TEST_SECRET.encode(), msg, hashlib.sha256).hexdigest()


CHECKOUT = {
    'full_name': 'Test Buyer', 'phone': '9876543210', 'address': 'Shop 12 Main Road',
    'pincode': '388001', 'city': 'Anand', 'state': 'Gujarat', 'email': 'buyer@example.com',
}


@override_settings(RAZORPAY_KEY_ID='rzp_test_key', RAZORPAY_SECRET_KEY=TEST_SECRET,
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class BaseShopTest(TestCase):
    def setUp(self):
        rzp_patch = patch('razorpay.resources.order.Order.create', fake_rzp_create)
        rzp_patch.start()
        self.addCleanup(rzp_patch.stop)
        self.user = User.objects.create(full_name='Buyer', email='buyer@example.com',
                                        password=make_password('pw'))
        cat = Category.objects.create(name='Roses', slug='roses')
        self.cheap = Product.objects.create(name='Mini', category=cat, original_price=100,
                                            price=100, stock_quantity=5)
        self.pricey = Product.objects.create(name='Grand', category=cat, original_price=5000,
                                             price=5000, stock_quantity=5)
        self.login()

    def login(self):
        session = self.client.session
        session['user_id'] = self.user.id
        session.save()

    def buy(self, product, qty=1, **extra):
        CartItem.objects.create(user=self.user, product=product, quantity=qty)
        return self.client.post(reverse('place_order'), {**CHECKOUT, **extra})


class PaymentVerificationTests(BaseShopTest):
    def test_valid_payment_marks_order_paid(self):
        # 'online' is what the real checkout form sends.
        self.buy(self.pricey, payment_mode='online')
        order = Order.objects.get()
        resp = self.client.post(reverse('confirm_payment'), {
            'razorpay_order_id': order.razorpay_order_id,
            'razorpay_payment_id': 'pay_1',
            'razorpay_signature': sign(order.razorpay_order_id, 'pay_1'),
        })
        self.assertRedirects(resp, reverse('order_success', args=[order.id]))
        self.assertEqual(Payment.objects.get(order=order).status, 'completed')

    def test_payment_for_cheap_order_cannot_pay_for_expensive_one(self):
        self.buy(self.cheap, payment_mode='upi')
        cheap_order = Order.objects.latest('id')
        self.buy(self.pricey, payment_mode='upi')
        pricey_order = Order.objects.latest('id')

        # Real payment + signature for the cheap order, sent while the expensive
        # order is the one waiting in the session.
        self.client.post(reverse('confirm_payment'), {
            'razorpay_order_id': cheap_order.razorpay_order_id,
            'razorpay_payment_id': 'pay_cheap',
            'razorpay_signature': sign(cheap_order.razorpay_order_id, 'pay_cheap'),
        })
        self.assertEqual(Payment.objects.get(order=pricey_order).status, 'pending')

        # Same proof, but claiming it belongs to the expensive order: rejected.
        self.client.post(reverse('confirm_payment'), {
            'razorpay_order_id': pricey_order.razorpay_order_id,
            'razorpay_payment_id': 'pay_cheap',
            'razorpay_signature': sign(cheap_order.razorpay_order_id, 'pay_cheap'),
        })
        self.assertEqual(Payment.objects.get(order=pricey_order).status, 'pending')

    def test_cannot_confirm_someone_elses_order(self):
        self.buy(self.pricey, payment_mode='upi')
        order = Order.objects.get()
        other = User.objects.create(full_name='Other', email='o@example.com', password='x')
        session = self.client.session
        session['user_id'] = other.id
        session.save()
        self.client.post(reverse('confirm_payment'), {
            'razorpay_order_id': order.razorpay_order_id,
            'razorpay_payment_id': 'pay_x',
            'razorpay_signature': sign(order.razorpay_order_id, 'pay_x'),
        })
        self.assertEqual(Payment.objects.get(order=order).status, 'pending')

    def test_razorpay_amount_matches_order_total(self):
        with patch('razorpay.resources.order.Order.create', autospec=True,
                   side_effect=fake_rzp_create) as create:
            self.buy(self.pricey, payment_mode='card')
        order = Order.objects.get()
        sent_amount = create.call_args.args[1]['amount']
        self.assertEqual(sent_amount, int(round(float(order.total_amount) * 100)))


class AbandonedOrderTests(BaseShopTest):
    def test_unpaid_online_order_releases_stock_coupon_and_slot(self):
        coupon = Coupon.objects.create(code='SAVE10', discount_percent=10,
                                       expiry=timezone.now().date() + timedelta(days=5))
        slot = DeliverySlot.objects.create(date=timezone.now().date(), slot_label='AM',
                                           slot_start='09:00', slot_end='11:00')
        self.buy(self.pricey, qty=2, payment_mode='online', coupon_code='save10', slot_id=slot.id)
        order = Order.objects.get()
        self.pricey.refresh_from_db(); coupon.refresh_from_db(); slot.refresh_from_db()
        self.assertEqual((self.pricey.stock_quantity, coupon.used_count, slot.booked_count), (3, 1, 1))

        # Not old enough yet: nothing happens.
        self.assertEqual(release_expired_online_orders(), 0)

        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=1))
        self.assertEqual(release_expired_online_orders(), 1)

        order.refresh_from_db(); self.pricey.refresh_from_db(); coupon.refresh_from_db(); slot.refresh_from_db()
        self.assertEqual(order.status, 'cancelled')
        self.assertEqual(Payment.objects.get(order=order).status, 'expired')
        self.assertEqual((self.pricey.stock_quantity, coupon.used_count, slot.booked_count), (5, 0, 0))
        # Running again doesn't give stock back twice.
        self.assertEqual(release_expired_online_orders(), 0)

    def test_paid_and_cod_orders_are_never_released(self):
        self.buy(self.cheap, payment_mode='cod')
        Order.objects.update(created_at=timezone.now() - timedelta(days=1))
        self.assertEqual(release_expired_online_orders(), 0)

    def test_razorpay_failure_gives_stock_back(self):
        with patch('razorpay.resources.order.Order.create', side_effect=Exception('down')):
            resp = self.buy(self.pricey, qty=2, payment_mode='upi')
        self.assertRedirects(resp, reverse('cart'), fetch_redirect_response=False)
        self.pricey.refresh_from_db()
        self.assertEqual(self.pricey.stock_quantity, 5)
        self.assertEqual(Order.objects.get().status, 'cancelled')

    def test_cancel_restores_stock_once(self):
        self.buy(self.cheap, qty=2, payment_mode='cod')
        order = Order.objects.get()
        self.client.post(reverse('cancel_order', args=[order.id]))
        self.client.post(reverse('cancel_order', args=[order.id]))
        self.cheap.refresh_from_db()
        self.assertEqual(self.cheap.stock_quantity, 5)


class InputValidationTests(BaseShopTest):
    def test_negative_flower_count_cannot_lower_price(self):
        self.client.post(reverse('custom_bouquet'), {
            'flowers': 'rose', 'flower_count': '-50', 'wrapping': 'classic'})
        bouquet = CustomBouquet.objects.get()
        self.assertEqual(bouquet.flower_count, 1)
        self.assertGreater(bouquet.price, 0)

    def test_unknown_wrapping_is_rejected(self):
        self.client.post(reverse('custom_bouquet'), {
            'flowers': 'rose', 'flower_count': '12', 'wrapping': 'free'})
        self.assertFalse(CustomBouquet.objects.exists())

    def test_text_in_number_fields_does_not_crash(self):
        r1 = self.client.post(reverse('add_to_cart', args=[self.cheap.id]), {'quantity': 'abc'})
        item = CartItem.objects.get()
        r2 = self.client.post(reverse('update_cart'), {'item_id': item.id, 'quantity': 'xyz'})
        r3 = self.client.post(reverse('update_cart'), {'item_id': 'nope', 'quantity': '1'})
        r4 = self.client.post(reverse('custom_bouquet'), {'flowers': 'rose', 'flower_count': 'many', 'wrapping': 'classic'})
        r5 = self.client.post(reverse('submit_review', args=[self.cheap.id]), {'rating': 'ten', 'comment': 'nice'})
        for r in (r1, r2, r3, r4, r5):
            self.assertEqual(r.status_code, 302)

    def test_update_cart_caps_at_stock(self):
        item = CartItem.objects.create(user=self.user, product=self.cheap, quantity=1)
        self.client.post(reverse('update_cart'), {'item_id': item.id, 'quantity': '999'})
        item.refresh_from_db()
        self.assertEqual(item.quantity, 5)

    def test_cannot_buy_more_than_stock(self):
        CartItem.objects.create(user=self.user, product=self.cheap, quantity=9)
        self.client.post(reverse('place_order'), {**CHECKOUT, 'payment_mode': 'cod'})
        self.assertFalse(Order.objects.exists())

    def test_unknown_payment_mode_is_rejected(self):
        self.buy(self.cheap, payment_mode='free')
        self.assertFalse(Order.objects.exists())


class PostOnlyDeleteTests(BaseShopTest):
    def test_remove_from_cart_needs_post(self):
        item = CartItem.objects.create(user=self.user, product=self.cheap, quantity=1)
        self.assertEqual(self.client.get(reverse('remove_from_cart', args=[item.id])).status_code, 405)
        self.assertTrue(CartItem.objects.filter(pk=item.pk).exists())
        self.client.post(reverse('remove_from_cart', args=[item.id]))
        self.assertFalse(CartItem.objects.filter(pk=item.pk).exists())

    def test_admin_product_delete_needs_post(self):
        admin = User.objects.create(full_name='Admin', email='a@example.com', password='x', role='admin')
        session = self.client.session
        session['admin_id'] = admin.id
        session.save()
        url = reverse('admin_product_delete', args=[self.cheap.id])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertTrue(Product.objects.filter(pk=self.cheap.pk).exists())
        self.client.post(url)
        self.assertFalse(Product.objects.filter(pk=self.cheap.pk).exists())
