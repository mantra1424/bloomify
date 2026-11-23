"""Request monitoring: an ID to follow each request through the logs, and its timing."""

import logging
import re
import time
import uuid

from django.conf import settings
from django.db import connection

logger = logging.getLogger('bloomapp.requests')
SAFE_ID = re.compile(r'^[A-Za-z0-9-]{8,64}$')


class RequestMonitoringMiddleware:
    """
    - Request ID: reuses the X-Request-ID the platform sends (Render does), or makes one,
      and returns it, so a customer's report can be matched to log lines.
    - Timing: added as a Server-Timing header (visible in the browser's dev tools).
    - Slow requests are logged as warnings with their database query count, the
      symptom to alert on before customers notice.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get('X-Request-ID', '')
        request.id = incoming if SAFE_ID.match(incoming) else uuid.uuid4().hex
        queries_before = len(connection.queries) if settings.DEBUG else None
        start = time.perf_counter()

        response = self.get_response(request)

        ms = (time.perf_counter() - start) * 1000
        response['X-Request-ID'] = request.id
        response['Server-Timing'] = f'app;dur={ms:.1f}'
        if ms >= settings.SLOW_REQUEST_MS and not request.path.startswith(('/static/', '/media/')):
            queries = '' if queries_before is None else f' queries={len(connection.queries) - queries_before}'
            logger.warning(
                'Slow request %s %s status=%s ms=%.0f%s id=%s',
                request.method,
                request.path,
                response.status_code,
                ms,
                queries,
                request.id,
            )
        return response
