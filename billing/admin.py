from django.contrib import admin, messages
from django.utils import timezone
from .models import (PromoCode, Referral, Transaction, Commission,
                     WithdrawalRequest, AppConfig, CrashReport)
from . import firebase_service as fb


@admin.register(CrashReport)
class CrashReportAdmin(admin.ModelAdmin):
    """Crashs/erreurs remontés par l'app mobile (consultation seule)."""
    list_display = ('created_at', 'platform', 'app_version', 'build_number',
                    'fatal', 'short_error', 'email')
    list_filter = ('fatal', 'platform', 'app_version')
    search_fields = ('uid', 'email', 'error', 'stack')
    readonly_fields = ('uid', 'email', 'platform', 'app_version', 'build_number',
                       'fatal', 'error', 'stack', 'created_at')
    date_hierarchy = 'created_at'

    @admin.display(description='Erreur')
    def short_error(self, obj):
        return (obj.error or '').splitlines()[0][:80] if obj.error else ''

    def has_add_permission(self, request):
        return False  # alimenté uniquement par l'app via l'API


@admin.register(AppConfig)
class AppConfigAdmin(admin.ModelAdmin):
    """Pilote la mise à jour de l'app mobile. À l'enregistrement, synchronise
    vers Firestore `config/app` (l'app lit ce doc au démarrage)."""
    list_display = ('latest_build', 'min_build', 'message', 'updated_at')
    actions = ['sync_now']

    def has_add_permission(self, request):
        # Enregistrement unique.
        return not AppConfig.objects.exists()

    def _sync(self, request, obj):
        try:
            fb.set_app_config(
                latest_build=obj.latest_build,
                min_build=obj.min_build,
                message=obj.message,
                store_url=obj.store_url,
            )
            self.message_user(
                request,
                "Synchronisé vers Firestore (config/app). "
                f"MAJ {'OBLIGATOIRE' if obj.min_build >= obj.latest_build else 'proposée'} "
                f"pour les builds < {obj.min_build}.",
                level=messages.SUCCESS,
            )
        except Exception as e:
            self.message_user(
                request, f"Enregistré, mais échec de la synchro Firestore : {e}",
                level=messages.ERROR)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        self._sync(request, obj)

    @admin.action(description="Resynchroniser vers Firestore maintenant")
    def sync_now(self, request, queryset):
        for obj in queryset:
            self._sync(request, obj)


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
