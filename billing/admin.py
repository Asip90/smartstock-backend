from django.contrib import admin
from .models import PromoCode, Referral, Transaction, Commission


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ('code', 'influencer_name', 'commission_pct', 'trial_months', 'active', 'created_at')
    search_fields = ('code', 'influencer_name')


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
