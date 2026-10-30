"""
Business rules for Petal & Stem, kept separate from views so they are easy to
read and test:

- pricing  – delivery charges, serviceable cities, coupons, custom bouquet price
- orders   – placing, cancelling and releasing orders (stock, coupons, slots)
- payments – Razorpay orders and signature checks
- emails   – customer notifications
"""
