from django.core.management.base import BaseCommand

from bloomapp.services.orders import release_expired_online_orders


class Command(BaseCommand):
    help = 'Cancel online orders whose payment was never completed and give their stock back.'

    def handle(self, *args, **options):
        count = release_expired_online_orders()
        self.stdout.write(self.style.SUCCESS(f'Released {count} unpaid order(s).'))
