"""Clear cached catalog data whenever something it is built from changes."""

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from bloomapp.models import Category, OrderItem, Product, Review
from bloomapp.services.cache import invalidate_catalog

# Product: names, prices, photos. Category: the menu. Review: ratings.
# OrderItem: the home page's bestseller order.
CATALOG_MODELS = (Product, Category, Review, OrderItem)


@receiver(post_save)
@receiver(post_delete)
def catalog_changed(sender, **kwargs):
    if sender in CATALOG_MODELS:
        invalidate_catalog()


@receiver(m2m_changed, sender=Product.extra_categories.through)
def product_categories_changed(sender, **kwargs):
    invalidate_catalog()
