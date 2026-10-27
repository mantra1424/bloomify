"""Customer sign up, log in, log out and account dashboard."""

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from bloomapp.forms import AddressForm, ProfileForm, SignupForm, first_error
from bloomapp.models import Order, SavedAddress


def _safe_next(request, default='home'):
    """Only follow ?next= links that stay on this site (stops open redirects)."""
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return next_url
    return default


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Welcome to Bloomify, {user.full_name}! 🌸')
            return redirect('home')
        messages.error(request, first_error(form))
    return render(request, 'bloomapp/auth/signup.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect(_safe_next(request))
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')
        user = authenticate(request, email=email, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f'Welcome back, {user.full_name}! 🌸')
            return redirect(_safe_next(request))
        # Same message either way, so the form doesn't reveal which emails exist.
        messages.error(request, 'Incorrect email or password.')
    return render(request, 'bloomapp/auth/login.html')


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, 'Logged out successfully.')
    return redirect('home')


@login_required
def user_dashboard(request):
    user = request.user
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_profile':
            form = ProfileForm(request.POST, user=user)
            if form.is_valid():
                form.save()
                update_session_auth_hash(request, user)  # stay logged in after a password change
                messages.success(request, 'Profile updated! ✅')
            else:
                messages.error(request, first_error(form))

        elif action == 'add_address':
            form = AddressForm(request.POST)
            if form.is_valid():
                form.save(user)
                messages.success(request, 'Address saved! 📍')
            else:
                messages.error(request, first_error(form))

        elif action == 'delete_address':
            SavedAddress.objects.filter(id=request.POST.get('address_id'), user=user).delete()
            messages.success(request, 'Address removed.')

        return redirect('dashboard')

    return render(
        request,
        'bloomapp/dashboard/dashboard.html',
        {
            'orders': Order.objects.filter(user=user).select_related('payment').order_by('-created_at'),
            'addresses': SavedAddress.objects.filter(user=user),
            'tab': request.GET.get('tab', 'orders'),
        },
    )
