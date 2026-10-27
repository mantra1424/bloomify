# 🌸 Bloomify — Complete Platform Documentation

## Table of Contents
1. [Project Structure](#structure)
2. [Authentication System](#auth)
3. [Product System](#products)
4. [Cart System](#cart)
5. [Checkout & Orders](#checkout)
6. [Wishlist System](#wishlist)
7. [Order Cancellation](#cancel)
8. [Search Autocomplete](#search)
9. [Newsletter](#newsletter)
10. [Admin Panel](#admin)
11. [Models Reference](#models)

---

## 1. Project Structure {#structure}

```
Bloomer/
├── bloomapp/
│   ├── models.py          ← All database models
│   ├── views.py           ← All view functions (logic)
│   ├── urls.py            ← URL routing
│   ├── static/css/        ← Stylesheets
│   └── templates/
│       └── bloomapp/
│           ├── base.html              ← Shared navbar/footer
│           ├── products/list.html     ← Product listing
│           ├── products/detail.html   ← Product detail
│           ├── wishlist/wishlist.html ← Wishlist page
│           ├── checkout/              ← Checkout flow
│           ├── dashboard/             ← User dashboard
│           └── admin_panel/           ← Admin pages
└── bloomproject/
    └── urls.py            ← Project-level URL config
```

---

## 2. Authentication System {#auth}

### How Login Works
```
User fills login form → POST /login/
  → login_view() in views.py
  → Checks email + password using check_password()
  → On success: stores user_id, user_name in request.session
  → Redirects to dashboard or next page
```

### Session-Based Auth (Custom, not Django's built-in)
- No `django.contrib.auth` User model used
- Custom `User` model in `models.py`
- `get_current_user(request)` helper reads `request.session['user_id']`
- `@login_required_custom` decorator redirects to `/login/` if not logged in
- `@admin_required` decorator checks `user.is_admin == True`

### Signup Flow
```
POST /signup/ → signup_view()
  → Validates email uniqueness
  → Hashes password with make_password()
  → Creates User object
  → Sets session → redirects to home
```

---

## 3. Product System {#products}

### Product Listing (`products_list` view)
```python
# Filters applied in order:
1. category filter (slug match on primary OR extra_categories)
2. price range filter (min_price, max_price)
3. text search (name, description, flowers)
4. occasion filter (occasion_tags contains value)
5. sorting (newest / price_asc / price_desc / popular)

# Wishlist IDs passed to template:
wishlist_ids = set of product PKs user has wishlisted
→ Template uses: {% if product.pk in wishlist_ids %}
```

### Product Detail (`product_detail` view)
```python
# Loads:
- Product by PK (only 'available' status)
- All reviews for the product
- Smart recommendations (same category, sorted by order count)
- in_wishlist = True/False for current user

# Recently Viewed: pushed to session (max 6)
```

### Stock & Urgency Badges
| Condition | What Shows |
|---|---|
| `stock_quantity == 0` | "Out of Stock" red badge on image |
| `stock_quantity <= 5 and > 0` | "⚡ Only X left!" orange badge |
| `status == 'unavailable'` | Product hidden from listing |

### Out of Stock Auto-Update
When an order is placed, `place_order` view decrements stock:
```python
item.product.stock_quantity -= item.quantity
if item.product.stock_quantity <= 0:
    item.product.status = 'unavailable'
item.product.save()
```

---

## 4. Cart System {#cart}

### Cart Storage
- Cart items stored in **database** (`CartItem` model)
- Linked to `User` (if logged in) or session
- `cart_count` passed to every page via context processor in `base.html`

### Add to Cart (AJAX)
```
Click "Add" button → fetch POST /cart/add/<pk>/
  → add_to_cart() view
  → Creates or increments CartItem
  → Returns JSON or redirect
  → JS updates cart badge count without page reload
```

### Cart Operations
| URL | Function | What it does |
|---|---|---|
| `/cart/` | `cart_view` | Shows all cart items |
| `/cart/add/<pk>/` | `add_to_cart` | Add product to cart |
| `/cart/update/` | `update_cart` | Change quantity |
| `/cart/remove/<id>/` | `remove_from_cart` | Delete cart item |

---

## 5. Checkout & Orders {#checkout}

### Checkout Flow
```
1. User clicks Checkout → /checkout/
2. checkout_view() loads:
   - User's cart items
   - Delivery zones (for charge calculation)
   - Saved addresses
   - Available coupons

3. User fills form:
   - Delivery address
   - Delivery date/time
   - Payment mode (COD / UPI / Card)
   - Optional gift message

4. POST /order/place/ → place_order()
   - Validates stock availability
   - Decrements stock for each item
   - Creates Order + OrderItems
   - Clears cart
   - Sends confirmation email
   - Redirects to /orders/<pk>/success/
```

### Order Status Flow
```
placed → packed → out_for_delivery → delivered
                                   ↘ cancelled
```

### Coupon Logic
```python
POST /checkout/apply-coupon/ → apply_coupon_ajax()
  → Finds coupon by code
  → Checks: is_active, expiry_date, min_order_value
  → Calculates discount (percent or fixed)
  → Returns JSON {discount_amount, final_total}
```

---

## 6. Wishlist System {#wishlist}

### Model
```python
class Wishlist(models.Model):
    user    = ForeignKey(User)
    product = ForeignKey(Product)
    added_at = DateTimeField(auto_now_add=True)
    # unique_together = (user, product) — no duplicates
```

### Toggle Wishlist (AJAX)
```
Click heart icon → fetch POST /wishlist/toggle/<pk>/
  → toggle_wishlist() view
  → If exists: DELETE → in_wishlist=False
  → If not: CREATE → in_wishlist=True
  → Returns JSON {in_wishlist, message}
  → JS updates heart fill without page reload
```

### Heart Button States
| State | Visual | Fill |
|---|---|---|
| Not wishlisted | 🤍 hollow | fill="none" |
| Wishlisted | ❤️ filled red | fill="currentColor" |
| Not logged in | Redirects to /login/ | — |

---

## 7. Order Cancellation {#cancel}

### Logic
```python
POST /orders/<pk>/cancel/ → cancel_order()
  1. Verifies order belongs to current user
  2. Checks order.status == 'placed' (only cancellable if placed)
  3. For each OrderItem:
       product.stock_quantity += item.quantity  ← restores stock
       product.save()
  4. order.status = 'cancelled'
  5. Shows success message → redirects to dashboard
```

### Rules
- Only **"Placed"** orders can be cancelled
- Stock is **automatically restored** on cancellation
- Cancel button only appears in dashboard for "placed" orders

---

## 8. Search Autocomplete {#search}

### How it Works
```
User types in navbar search box (≥ 2 chars)
  → 220ms debounce delay
  → GET /products/autocomplete/?q=<query>
  → search_autocomplete() view
  → Filters: status='available' AND (name OR flowers OR occasion_tags contains q)
  → Returns JSON [{id, name, price, image, url, category}]
  → JS renders dropdown with image + name + price
```

### Debounce
- Waits 220ms after last keystroke before firing request
- Prevents flooding the server on every keypress

---

## 9. Newsletter {#newsletter}

### Model
```python
class NewsletterSubscriber(models.Model):
    email         = EmailField(unique=True)
    subscribed_at = DateTimeField(auto_now_add=True)
    is_active     = BooleanField(default=True)
```

### Subscribe Flow
```
User types email in footer form → JS fetch POST /newsletter/subscribe/
  → newsletter_subscribe() view
  → get_or_create(email=email)
  → If created: "Subscribed! Thank you 🌸"
  → If exists: "You're already subscribed!"
  → Returns JSON → JS replaces form with success message
```

---

## 10. Admin Panel {#admin}

### Admin Auth
- Separate login at `/admin-panel/login/`
- Checks `user.is_admin == True`
- `@admin_required` decorator protects all admin views

### Dashboard (`admin_dashboard`)
```python
# Loads:
- Today's stats (orders, revenue)
- Recent 10 orders
- Out of Stock products (stock_quantity=0)
- Low Stock products (stock_quantity 1-5)
- Collapsible alert panels auto-expand if any alerts exist
```

### Sales Report (`admin_sales_report`)
```python
# Filters: date_from, date_to, status, payment mode
# Calculates:
- total_revenue = sum of total_amount
- total_orders = count
- avg_order_val = revenue / orders
- status_breakdown = group by status
- payment_breakdown = group by payment_mode
- top_products = top 10 by revenue

# Export: CSV download, PDF (html2pdf.js)
```

### Bulk Stock Edit (URL: `/admin-panel/products/bulk-stock/`)
- Table of all products with editable stock inputs
- Single POST saves all changes at once

### Admin Order Notes
- Internal notes per order (not visible to customers)
- Saved via AJAX inline in orders list

---

## 11. Models Reference {#models}

| Model | Key Fields | Purpose |
|---|---|---|
| `User` | email, password, is_admin | Custom user accounts |
| `Category` | name, slug, icon | Product categories |
| `Product` | name, price, stock_quantity, status | Products |
| `CartItem` | user, product, quantity | Shopping cart |
| `Order` | user, status, total_amount, gift_message | Orders |
| `OrderItem` | order, product, quantity, price | Items in order |
| `Payment` | order, razorpay_order_id, status | Payment records |
| `Review` | user, product, rating, comment | Product reviews |
| `Coupon` | code, discount_type, value, expiry | Discount codes |
| `Wishlist` | user, product | Saved products |
| `NewsletterSubscriber` | email | Email signups |
| `SavedAddress` | user, label, address | Delivery addresses |
| `ContactMessage` | name, email, subject, message | Contact form |
| `DeliveryZone` | city, charge | Delivery pricing |

---

## Key Helper Functions

| Function | Location | Purpose |
|---|---|---|
| `get_current_user(request)` | views.py | Get logged-in User object from session |
| `login_required_custom` | views.py | Decorator: redirect to login if not authenticated |
| `admin_required` | views.py | Decorator: redirect if not admin |
| `product.is_in_stock` | models.py | Property: True if stock_quantity > 0 |
| `product.discount_percent` | models.py | Property: % discount from original_price |
| `product.avg_rating` | models.py | Property: average star rating |
| `product.get_image` | models.py | Property: returns first available image URL |
| `order.status_display` | models.py | Property: human-readable status |

---

*Generated for Bloomify — Fresh Flower Bouquets Platform*
*Built with Django 4.2 + Python 3.9*
