# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from django.utils.encoding import python_2_unicode_compatible

from django.db import models

# Create your models here.

from django.contrib.auth.models import User, Group
from django.db.models.signals import post_save
from django.dispatch import receiver
from datetime import date, timedelta
from django.utils import timezone
from decimal import Decimal
import pytz

@python_2_unicode_compatible
class Parent(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    is_billing_contact = models.BooleanField("Billing Contact", default=True)

    def __str__(self):
        return str(self.user)

@python_2_unicode_compatible
class Student(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    parents = models.ManyToManyField(Parent, blank=True)
    date_of_birth = models.DateField(blank=True, null=True)
    is_voice_student = models.BooleanField("Learning Voice", default=False)
    is_piano_student = models.BooleanField("Learning Piano", default=False)

    #add more or change them as needed
    PAYMENT_PER_LESSON_FLAT = 'PER_LESSON_FLAT'
    PAYMENT_PER_LESSON_DEAL = 'PER_LESSON_DEAL'
    PAYMENT_PER_LESSON_TRAVEL_5 = 'PER_LESSON_TRAVEL_5'
    PAYMENT_PER_LESSON_TRAVEL_10 = 'PER_LESSON_TRAVEL_10'
    PAYMENT_PER_LESSON_TRAVEL_15 = 'PER_LESSON_TRAVEL_15'
    PAYMENT_PER_LESSON_TRAVEL_20 = 'PER_LESSON_TRAVEL_20'
    PAYMENT_PLANS = [
        (PAYMENT_PER_LESSON_FLAT, 'Individual Lessons (Flat Rates)'),
        (PAYMENT_PER_LESSON_DEAL, 'Individual Lessons (Deal Rates)'),
        (PAYMENT_PER_LESSON_TRAVEL_5, 'Individual Lessons (+$5 Travel)'),
        (PAYMENT_PER_LESSON_TRAVEL_10, 'Individual Lessons (+$10 Travel)'),
        (PAYMENT_PER_LESSON_TRAVEL_15, 'Individual Lessons (+$15 Travel)'),
        (PAYMENT_PER_LESSON_TRAVEL_20, 'Individual Lessons (+$20 Travel)'),
    ]
    billing_plan = models.CharField(choices=PAYMENT_PLANS, max_length=200, null=True)
    is_billing_contact = models.BooleanField("Billing Contact", default=True)

    def __str__(self):
        return str(self.user)

@receiver(post_save, sender=User)
def create_profiles(sender, instance, created, **kwargs):

    if created:
        Student.objects.create(user=instance)
        students_group = Group.objects.get(name='Students')
        instance.groups.add(students_group)
    else:
        if Student.objects.filter(user=instance).exists():
            for lesson in instance.student.lesson_set.filter(status=Lesson.STATUS_PLANNED):
                lesson.save()

        if instance.groups.filter(name='Parents').exists():
            Parent.objects.get_or_create(user=instance)
            Student.objects.filter(user=instance).delete()
        elif Parent.objects.filter(user=instance).exists() and not instance.groups.filter(name='Parents').exists():
            Parent.objects.filter(user=instance).delete()

@python_2_unicode_compatible
class Lesson(models.Model):
    student = models.ForeignKey(Student)
    summary = models.CharField(max_length=255)
    is_makeup_lesson = models.BooleanField(default=False)
    time_start = models.DateTimeField("Start Time", default=timezone.now)

    #add more or change as needed
    DURATION_30_MINUTES = '30min'
    DURATION_45_MINUTES = '45min'
    DURATION_1_HOUR = '1hr'
    DURATION_1_HOUR_30_MINUTES = '1hr30min'
    DURATION_TIMES = [
        (DURATION_30_MINUTES, '30 Minutes'),
        (DURATION_45_MINUTES, '45 Minutes'),
        (DURATION_1_HOUR, '1 Hour'),
        (DURATION_1_HOUR_30_MINUTES, '1 Hour 30 Minutes'),
    ]
    duration = models.CharField(choices=DURATION_TIMES, max_length=50, null=True)

    #add more or change as needed
    STATUS_PLANNED = 'PLANNED'
    STATUS_LATE_CANCELLATION = 'LATE_CANCELLATION'
    STATUS_CANCELLATION_MAKEUP = 'CANCELLATION_MAKEUP'
    STATUS_CANCELLATION_CREDIT = 'CANCELLATION_CREDIT'
    STATUS_ATTENDED = 'ATTENDED'
    STATUS_CHOICES = [
        (STATUS_PLANNED, 'Planned'),
        (STATUS_LATE_CANCELLATION, 'Late Cancellation'),
        (STATUS_CANCELLATION_MAKEUP, 'Cancellation (Makeup)'),
        (STATUS_CANCELLATION_CREDIT, 'Cancellation (Credit)'),
        (STATUS_ATTENDED, 'Attended'),
    ]
    status = models.CharField(choices=STATUS_CHOICES, default=STATUS_PLANNED, max_length=50)
    gcal_vevent_uid = models.CharField(default=None, max_length=255, null=True)
    gcal_vevent_recurrence_id = models.DateTimeField(default=None, null=True)
    gcal_vevent_sequence = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['time_start']

    def __str__(self):
        return str(self.summary)

@receiver(post_save, sender=Lesson)
def manage_invoice(sender, instance, created, **kwargs):

    if not instance.student.billing_plan:
        return

    invoice = Invoice.objects.get_or_create(student=instance.student, lesson=instance)[0]

    if instance.status in [Lesson.STATUS_PLANNED, Lesson.STATUS_ATTENDED, Lesson.STATUS_CANCELLATION_CREDIT, Lesson.STATUS_LATE_CANCELLATION]:
        if instance.status == Lesson.STATUS_CANCELLATION_CREDIT:
            invoice.payment_status = Invoice.PAYMENT_STATUS_CREDIT
        else:
            invoice.payment_status = Invoice.PAYMENT_STATUS_UNPAID
        
        invoice.summary = "%s %sLesson%s" % (instance.duration, "(Makeup) " if instance.is_makeup_lesson else "", " (Late Cancellation)" if instance.status == Lesson.STATUS_LATE_CANCELLATION else "",)
        invoice.date_created = pytz.timezone('US/Pacific').normalize(instance.time_start.astimezone(pytz.timezone('US/Pacific')))
        invoice.date_due = date(instance.time_start.year, instance.time_start.month, 1)

        #add or change prices as needed
        if instance.duration == Lesson.DURATION_30_MINUTES:
            if instance.student.billing_plan == Student.PAYMENT_PER_LESSON_FLAT:
                invoice.subtotal = Decimal('35.00')
                invoice.travel_fee = Decimal('0.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_DEAL:
                invoice.subtotal = Decimal('30.00')
                invoice.travel_fee = Decimal('0.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_TRAVEL_5:
                invoice.subtotal = Decimal('35.00')
                invoice.travel_fee = Decimal('5.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_TRAVEL_10:
                invoice.subtotal = Decimal('35.00')
                invoice.travel_fee = Decimal('10.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_TRAVEL_15:
                invoice.subtotal = Decimal('35.00')
                invoice.travel_fee = Decimal('15.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_TRAVEL_20:
                invoice.subtotal = Decimal('35.00')
                invoice.travel_fee = Decimal('20.00')
        elif instance.duration == Lesson.DURATION_45_MINUTES:
            if instance.student.billing_plan == Student.PAYMENT_PER_LESSON_FLAT:
                invoice.subtotal = Decimal('50.00')
                invoice.travel_fee = Decimal('0.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_DEAL:
                invoice.subtotal = Decimal('45.00')
                invoice.travel_fee = Decimal('0.00')
        elif instance.duration == Lesson.DURATION_1_HOUR:
            if instance.student.billing_plan == Student.PAYMENT_PER_LESSON_FLAT:
                invoice.subtotal = Decimal('65.00')
                invoice.travel_fee = Decimal('0.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_DEAL:
                invoice.subtotal = Decimal('60.00')
                invoice.travel_fee = Decimal('0.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_TRAVEL_5:
                invoice.subtotal = Decimal('65.00')
                invoice.travel_fee = Decimal('5.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_TRAVEL_10:
                invoice.subtotal = Decimal('65.00')
                invoice.travel_fee = Decimal('10.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_TRAVEL_15:
                invoice.subtotal = Decimal('65.00')
                invoice.travel_fee = Decimal('15.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_TRAVEL_20:
                invoice.subtotal = Decimal('65.00')
                invoice.travel_fee = Decimal('20.00')
        elif instance.duration == Lesson.DURATION_1_HOUR_30_MINUTES:
            if instance.student.billing_plan == Student.PAYMENT_PER_LESSON_FLAT:
                invoice.subtotal = Decimal('95.00')
                invoice.travel_fee = Decimal('0.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_DEAL:
                invoice.subtotal = Decimal('90.00')
                invoice.travel_fee = Decimal('0.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_TRAVEL_5:
                invoice.subtotal = Decimal('95.00')
                invoice.travel_fee = Decimal('5.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_TRAVEL_10:
                invoice.subtotal = Decimal('95.00')
                invoice.travel_fee = Decimal('10.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_TRAVEL_15:
                invoice.subtotal = Decimal('95.00')
                invoice.travel_fee = Decimal('15.00')
            elif instance.student.billing_plan == Student.PAYMENT_PER_LESSON_TRAVEL_20:
                invoice.subtotal = Decimal('95.00')
                invoice.travel_fee = Decimal('20.00')

    elif instance.status == Lesson.STATUS_CANCELLATION_MAKEUP:
        invoice.summary = "MUST RESCHEDULE: %s %sLesson" % (instance.duration, "(Makeup) " if instance.is_makeup_lesson else "")
        invoice.payment_status = Invoice.PAYMENT_STATUS_VOID
        invoice.subtotal = Decimal('0.00')
        invoice.travel_fee = Decimal('0.00')

    invoice.save()

def default_due_date():
    return date(date.today().year, date.today().month, 1)

@python_2_unicode_compatible
class Invoice(models.Model):
    student = models.ForeignKey(Student)
    lesson = models.ForeignKey(Lesson, blank=True, null=True)
    summary = models.CharField(max_length=2048)
    date_created = models.DateField(default=date.today)
    date_due = models.DateField(default=default_due_date, blank=True, null=True)
    subtotal = models.DecimalField(decimal_places=2, max_digits=9, default=Decimal('0.00'))
    travel_fee = models.DecimalField(decimal_places=2, max_digits=9, default=Decimal('0.00'))

    #add more or change as needed
    PAYMENT_STATUS_UNPAID = 'UNPAID'
    PAYMENT_STATUS_PAID = 'PAID'
    PAYMENT_STATUS_CREDIT = 'CREDIT'
    PAYMENT_STATUS_VOID = 'VOID'
    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_STATUS_UNPAID, 'Unpaid'),
        (PAYMENT_STATUS_PAID, 'Paid'),
        (PAYMENT_STATUS_CREDIT, 'Credit'),
        (PAYMENT_STATUS_VOID, 'Void'),
    ]
    payment_status = models.CharField(choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_STATUS_UNPAID, max_length=50)

    class Meta:
        ordering = ['date_created']

    def __str__(self):
        return str(self.summary)


