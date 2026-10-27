"""Admin-panel login/logout. Uses the same accounts as the shop; only staff/admins get in."""
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST


def admin_login(request):
    if request.user.is_authenticated and request.user.is_staff_member():
        return redirect('admin_dashboard')
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        user = authenticate(request, email=email, password=request.POST.get('password', ''))
        if user is not None and user.is_staff_member():
            login(request, user)
            messages.success(request, f'Welcome, {user.full_name}!')
            return redirect('admin_dashboard')
        messages.error(request, 'Invalid credentials or insufficient permissions.')
    return render(request, 'bloomapp/admin_panel/login.html')


@require_POST
def admin_logout(request):
    logout(request)
    return redirect('admin_login')
