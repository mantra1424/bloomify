"""Admin product and coupon management (admins only; staff can view products)."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from bloomapp.forms import CouponForm, ProductForm, first_error
from bloomapp.models import Category, Coupon, Product
from bloomapp.permissions import admin_role_required, staff_required


@staff_required
def admin_products(request):
    return render(
        request,
        'bloomapp/admin_panel/products.html',
        {
            'admin_user': request.admin_user,
            'products': Product.objects.select_related('category')
            .prefetch_related('extra_categories')
            .order_by('-created_at'),
            'categories': Category.objects.all(),
            'is_staff': not request.admin_user.is_admin(),
        },
    )


@admin_role_required
@require_POST
def admin_product_add(request):
    form = ProductForm(request.POST, request.FILES)
    if form.is_valid():
        form.save()
        messages.success(request, 'Product added successfully!')
    else:
        messages.error(request, f'Could not add product: {first_error(form)}')
    return redirect('admin_products')


@admin_role_required
@require_POST
def admin_product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    data = request.POST.copy()
    # The edit dialog doesn't show every field; keep current values for the rest.
    for field in ('flowers', 'occasion_tags', 'description'):
        if field not in data:
            data[field] = getattr(product, field)
    form = ProductForm(data, request.FILES, instance=product)
    if form.is_valid():
        form.save()
        messages.success(request, 'Product updated!')
    else:
        messages.error(request, f'Could not update product: {first_error(form)}')
    return redirect('admin_products')


@admin_role_required
@require_POST
def admin_product_delete(request, pk):
    get_object_or_404(Product, pk=pk).delete()
    messages.success(request, 'Product deleted.')
    return redirect('admin_products')


@admin_role_required
def admin_coupons(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            form = CouponForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Coupon created!')
            else:
                messages.error(request, first_error(form))
        elif action == 'toggle':
            coupon = Coupon.objects.filter(id=request.POST.get('coupon_id')).first()
            if coupon:
                coupon.is_active = not coupon.is_active
                coupon.save(update_fields=['is_active'])
                messages.success(request, 'Coupon status toggled.')
        elif action == 'delete':
            Coupon.objects.filter(id=request.POST.get('coupon_id')).delete()
            messages.success(request, 'Coupon deleted.')
        return redirect('admin_coupons')

    return render(
        request,
        'bloomapp/admin_panel/coupons.html',
        {
            'admin_user': request.admin_user,
            'coupons': Coupon.objects.order_by('-created_at'),
        },
    )
