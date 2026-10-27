from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    CartItem,
    Category,
    ContactMessage,
    Coupon,
    CustomBouquet,
    DeliverySlot,
    DeliveryZone,
    NewsletterSubscriber,
    Order,
    OrderItem,
    Payment,
    Product,
    Review,
    SavedAddress,
    User,
    Wishlist,
)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Django's user admin, adapted for email logins and our extra fields."""

    ordering = ('-created_at',)
    list_display = ('full_name', 'email', 'phone', 'role', 'is_active', 'created_at')
    list_filter = ('role', 'is_active', 'is_staff')
    search_fields = ('full_name', 'email', 'phone')
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Profile', {'fields': ('full_name', 'phone', 'role')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'full_name', 'role', 'password1', 'password2')}),
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'status')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'extra_categories_list', 'price', 'stock_quantity', 'is_featured', 'status')
    list_filter = ('category', 'extra_categories', 'status', 'is_featured')
    search_fields = ('name',)
    filter_horizontal = ('extra_categories',)

    def extra_categories_list(self, obj):
        cats = obj.extra_categories.all()
        return ', '.join(c.name for c in cats) if cats else '—'

    extra_categories_list.short_description = 'Also In'


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('product', 'user', 'rating', 'created_at')


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ('zone_name', 'pincode_prefix', 'delivery_charge')


@admin.register(DeliverySlot)
class DeliverySlotAdmin(admin.ModelAdmin):
    list_display = ('date', 'slot_label', 'booked_count', 'max_orders', 'is_available')


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_percent', 'used_count', 'max_uses', 'expiry', 'is_active')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'full_name', 'total_amount', 'payment_mode', 'status', 'created_at')
    list_filter = ('status', 'payment_mode')


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'quantity', 'price', 'line_total')


admin.site.register(SavedAddress)
admin.site.register(CustomBouquet)
admin.site.register(CartItem)
admin.site.register(Payment)
admin.site.register(ContactMessage)
admin.site.register(Wishlist)
admin.site.register(NewsletterSubscriber)
