"""Access rules for the Bloomify admin panel (separate from /django-admin/)."""

from functools import wraps

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect


def staff_required(view_fn):
    """Staff and admins only. Others are sent to the admin-panel login."""

    @wraps(view_fn)
    def wrapper(request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated or not user.is_staff_member():
            return redirect('admin_login')
        request.admin_user = user
        return view_fn(request, *args, **kwargs)

    return wrapper


def admin_role_required(view_fn):
    """Admins only. Staff are sent back to the dashboard (or get a 403 for JSON)."""

    @wraps(view_fn)
    @staff_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_admin():
            if request.path.startswith('/admin-panel/api/'):
                return JsonResponse({'error': 'Forbidden'}, status=403)
            messages.error(request, '🚫 Admin access required.')
            return redirect('admin_dashboard')
        return view_fn(request, *args, **kwargs)

    return wrapper
