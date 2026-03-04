"""
Add referral users for a given referrer (by phone number).
Creates N new users with referred_by=referrer so their referral count increases.

Usage:
  python manage.py add_referrals 9182351381 --count 20
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from accounts.models import Wallet

User = get_user_model()


def normalize_phone(phone):
    """Normalize to digits only for lookup."""
    if not phone:
        return ""
    s = str(phone).strip().replace("+", "").replace(" ", "").replace("-", "")
    return "".join(c for c in s if c.isdigit())


class Command(BaseCommand):
    help = "Add N referral users for a referrer identified by phone number (e.g. 9182351381)"

    def add_arguments(self, parser):
        parser.add_argument(
            "phone",
            type=str,
            help="Referrer phone number (e.g. 9182351381 or +919182351381)",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=20,
            help="Number of referral users to create (default: 20)",
        )

    def handle(self, *args, **options):
        phone = options["phone"]
        count = options["count"]
        if count < 1 or count > 500:
            self.stdout.write(self.style.ERROR("--count must be between 1 and 500."))
            return

        normalized = normalize_phone(phone)
        if not normalized:
            self.stdout.write(self.style.ERROR("Invalid phone number."))
            return

        # Find referrer: try exact match and with/without leading 91
        referrer = (
            User.objects.filter(phone_number=phone).first()
            or User.objects.filter(phone_number=normalized).first()
            or User.objects.filter(phone_number=f"+{normalized}").first()
            or User.objects.filter(phone_number=f"91{normalized}" if not normalized.startswith("91") else normalized).first()
        )
        if not referrer:
            # Try by phone_number containing this digits
            referrer = User.objects.filter(phone_number__icontains=normalized[-10:] if len(normalized) >= 10 else normalized).first()
        if not referrer:
            self.stdout.write(
                self.style.ERROR(f"No user found with phone number like: {phone}")
            )
            return

        self.stdout.write(f"Referrer: {referrer.username} (id={referrer.pk}, phone={referrer.phone_number})")
        self.stdout.write(f"Creating {count} referral user(s)...")

        import random
        created = 0
        base_phone = 9700000000  # 10-digit base for unique dummy phones
        existing_phones = set(
            User.objects.filter(phone_number__startswith="97").values_list("phone_number", flat=True)
        )
        used_phones = set()
        for i in range(1, count + 1):
            username = f"ref_{referrer.pk}_{i}"
            while User.objects.filter(username=username).exists():
                username = f"ref_{referrer.pk}_{i}_{random.randint(100000, 999999)}"
            # Unique phone: 97 + 8 digits (base + offset)
            candidate_phone = str(base_phone + i)
            while candidate_phone in existing_phones or candidate_phone in used_phones:
                base_phone += 100
                candidate_phone = str(base_phone + i)
            used_phones.add(candidate_phone)
            existing_phones.add(candidate_phone)

            try:
                user = User(
                    username=username,
                    phone_number=candidate_phone,
                    email=f"{username}@referral.local",
                    referred_by=referrer,
                    is_active=True,
                )
                user.set_unusable_password()
                user.save()
                Wallet.objects.get_or_create(user=user, defaults={"balance": 0})
                created += 1
                if created % 5 == 0:
                    self.stdout.write(f"  Created {created}/{count}...")
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed to create referral {i}: {e}")
                )

        referrer.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Added {created} referrals for {referrer.username} (total referrals now: {getattr(referrer, 'total_referrals_count', referrer.referrals.count())})."
            )
        )
