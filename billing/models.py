from django.db import models
from django.utils import timezone
from datetime import timedelta


class PromoCode(models.Model):
    code = models.CharField(max_length=40, unique=True)
    influencer_name = models.CharField(max_length=120)
    influencer_id = models.CharField(max_length=120, blank=True)
    commission_pct = models.PositiveIntegerField(default=25)
    trial_months = models.PositiveIntegerField(default=3)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.code} ({self.influencer_name})'


class Referral(models.Model):
    """Lie un utilisateur (filleul) au code promo utilisé à l'inscription."""
    promo_code = models.ForeignKey(PromoCode, on_delete=models.PROTECT, related_name='referrals')
    referred_uid = models.CharField(max_length=128, unique=True)
    referred_email = models.EmailField(blank=True)
    signed_up_at = models.DateTimeField(auto_now_add=True)
    first_year_end = models.DateTimeField()

    def save(self, *args, **kwargs):
        if not self.first_year_end:
            self.first_year_end = timezone.now() + timedelta(days=365)
        super().save(*args, **kwargs)

    def is_within_first_year(self):
        return timezone.now() <= self.first_year_end


class Transaction(models.Model):
    PLAN_CHOICES = [('monthly', 'Mensuel'), ('yearly', 'Annuel')]
    STATUS_CHOICES = [('pending', 'En attente'), ('paid', 'Payé'), ('failed', 'Échoué')]

    uid = models.CharField(max_length=128, db_index=True)
    email = models.EmailField(blank=True)
    plan = models.CharField(max_length=10, choices=PLAN_CHOICES)
    amount = models.PositiveIntegerField()  # FCFA
    fedapay_id = models.CharField(max_length=64, blank=True, db_index=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.uid} {self.plan} {self.amount} ({self.status})'


class Commission(models.Model):
    STATUS_CHOICES = [('pending', 'À verser'), ('paid', 'Versée')]
    referral = models.ForeignKey(Referral, on_delete=models.CASCADE, related_name='commissions')
    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE)
    amount = models.PositiveIntegerField()  # FCFA (25% du paiement)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.referral.promo_code.code} -> {self.amount} ({self.status})'
