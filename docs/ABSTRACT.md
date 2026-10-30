# Project abstract

**Title:** Petal & Stem — Online Flower Bouquet Ordering and Delivery Management System Using Django

**Abstract:**
Petal & Stem is a full-stack web application built with Python and Django that lets customers
browse, customise and order flower bouquets online, and lets a florist manage products, orders
and deliveries from a role-based admin panel. Customers can search and filter bouquets by
occasion, design a custom bouquet (flowers, stem count, wrapping and message card), apply coupon
codes, choose a delivery slot, and pay securely online through Razorpay (UPI, cards, netbanking)
or by cash on delivery. Delivery charges are calculated by city, distance and delivery speed,
and customers can track or cancel their orders and receive email confirmations.

Staff and administrators use a separate admin panel with a sales dashboard, stock alerts, an order
status workflow, product and coupon management, and filterable sales reports with CSV and PDF
export. Payments are verified with Razorpay signatures and a signed webhook; unpaid orders expire
automatically and release their stock. Stock, coupon and slot bookings are made safely inside
database transactions so that simultaneous orders cannot oversell.

The system follows production practices: business rules are separated into a tested service
layer, all input is validated with Django forms, and authentication uses Django's built-in system
with brute-force protection and password reset. The project includes 218 automated tests (90%
coverage), continuous integration on GitHub Actions with PostgreSQL, Docker packaging, and
one-click deployment to Render.

**Key technologies:** Python 3.14, Django 6.1, PostgreSQL, Razorpay, HTML/CSS/JavaScript,
Chart.js, pytest, GitHub Actions, Docker, Render.
