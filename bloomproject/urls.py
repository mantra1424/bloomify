from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', include('bloomapp.urls')),
]

# Uploaded images: served by Django in development or when SERVE_MEDIA is on (demo).
# With S3 storage they are served straight from the bucket instead.
if settings.DEBUG or settings.SERVE_MEDIA:
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
