# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

# Register your models here.

from .models import Parent, Student, Lesson, Invoice

class ProfileInline(admin.StackedInline):
    model = Student
    can_delete = True
    verbose_name_plural = 'Profile'
    fk_name = 'user'

class CustomUserAdmin(UserAdmin):
    inlines = (ProfileInline,)
    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'get_parents',
    )
    list_select_related = ('student',)

    def get_parents(self, instance):
        return ", ".join([str(parent) for parent in instance.student.parents.all()])
    get_parents.short_description = 'Parents'

class CustomLessonAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'summary',
        'is_makeup_lesson',
        'time_start',
        'duration',
        'status',
    )
    exclude = (
        'gcal_vevent_uid',
        'gcal_vevent_recurrence_id',
        'gcal_vevent_sequence',
    )
    list_filter = (
        'is_makeup_lesson',
        'duration',
        'status',
    )
    search_fields = (
        'summary',
        'student__user__username',
        'student__user__last_name',
        'student__user__first_name',
        'student__parents__user__username',
        'student__parents__user__last_name',
    )
    actions = [
        'mark_all_as_attended'
    ]
    
    def mark_all_as_attended(self, request, queryset):
        queryset.update(status=Lesson.STATUS_ATTENDED)
        self.message_user(request, "All lessons successfully marked as attended.")
    mark_all_as_attended.short_description = "Mark selected lessons as attended"

    def get_queryset(self, request):
        qs = super(CustomLessonAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qs
        else:
            return qs.filter(student__in=Student.objects.filter(parents=request.user.parent))

class CustomInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'lesson',
        'summary',
        'date_created',
        'date_due',
        'subtotal',
        'travel_fee',
        'payment_status',
    )
    list_filter = (
        'payment_status',
    )
    search_fields = (
        'summary',
        'student__user__username',
        'student__user__last_name',
        'student__user__first_name',
        'student__parents__user__username',
        'student__parents__user__last_name',
    )
    actions = [
        'mark_all_as_paid'
    ]

    def mark_all_as_paid(self, request, queryset):
        queryset.update(payment_status=Invoice.PAYMENT_STATUS_PAID)
        self.message_user(request, "All invoices successfully marked as paid.")
    mark_all_as_paid.short_description = "Mark selected invoices as paid"

    def get_queryset(self, request):
        qs = super(CustomInvoiceAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return qs
        else:
            return qs.filter(student__in=Student.objects.filter(parents=request.user.parent))


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

admin.site.register(Lesson, CustomLessonAdmin)
admin.site.register(Invoice, CustomInvoiceAdmin)











