from django.contrib import admin
from django.utils import timezone
from .models import PromoCode, Referral, Transaction, Commission, WithdrawalRequest


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'influencer_name', 'owner', 'commission_pct',
                    'trial_days', 'trial_months', 'effective_days', 'active', 'created_at')
    # Édition rapide directement depuis la liste (jours d'essai, commission, statut).
    list_editable = ('trial_days', 'trial_months', 'commission_pct', 'active')
    list_filter = ('active',)
    search_fields = ('code', 'influencer_name', 'owner__username')
    autocomplete_fields = ('owner',)

    @admin.display(description="Essai effectif (jours)")
    def effective_days(self, obj):
        return obj.trial_duration_days()


@admin.register(WithdrawalRequest)
class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = ('owner', 'amount', 'contact', 'status', 'created_at', 'processed_at')
    list_filter = ('status',)
    search_fields = ('owner__username', 'contact')
    actions = ['mark_paid', 'mark_rejected']

    @admin.action(description='Marquer comme payé')
    def mark_paid(self, request, queryset):
        queryset.update(status='paid', processed_at=timezone.now())

    @admin.action(description='Rejeter')
    def mark_rejected(self, request, queryset):
        queryset.update(status='rejected', processed_at=timezone.now())


@admin.register(Referral)
class ReferralAdmin(admin.ModelAdmin):
    list_display = ('promo_code', 'referred_uid', 'referred_email', 'signed_up_at', 'first_year_end')
    search_fields = ('referred_uid', 'referred_email')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('uid', 'plan', 'amount', 'status', 'fedapay_id', 'created_at', 'paid_at')
    list_filter = ('status', 'plan')
    search_fields = ('uid', 'email', 'fedapay_id')


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = ('referral', 'transaction', 'amount', 'status', 'created_at')
    list_filter = ('status',)
    actions = ['mark_paid']

    @admin.action(description='Marquer comme versée')
    def mark_paid(self, request, queryset):
        queryset.update(status='paid')
