"""Fill the catalog cache before the app takes traffic, so the first visitors don't all hit the database."""

from django.core.management.base import BaseCommand

from bloomapp.context_processors import _nav_categories
from bloomapp.services.cache import cached
from bloomapp.views.pages import _home_sections


class Command(BaseCommand):
    help = 'Pre-load cached catalog data (menu, home page sections)'

    def handle(self, *args, **options):
        cached('nav_categories', _nav_categories)
        cached('home', _home_sections)
        self.stdout.write('  ✅ Catalog cache warmed')
