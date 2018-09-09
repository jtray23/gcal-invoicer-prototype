from django.core.management.base import BaseCommand, CommandError
from studio.models import Parent, Student, Lesson, Invoice

from django.contrib.auth.models import User, Group
from django.core.mail import EmailMessage
from django.utils import timezone
from icalendar import Calendar
from datetime import date
from dateutil.relativedelta import relativedelta
from operator import itemgetter
from decimal import Decimal
import os

class Command(BaseCommand):
    help = 'Sends email alerts for Lessons and email all billing contacts oustanding Invoices'

    def handle(self, *args, **options):

        #assume dry run condition
        is_dry_run = True
        if os.environ['CVAR_DRY_RUN'] == 'False':
            is_dry_run = False

        #sets the day of the month that late fee emails wills trigger
        late_fee_activation_day = 11

        date_today = date.today()
        invoiced_students = []
        for student in Student.objects.all():

            if student not in invoiced_students:

                invoice_line_items = []
                invoice_billing_emails = []
                has_unpaid_invoices = False
                late_fee_added_for_billing_period = False
                for invoice in student.invoice_set.filter(date_created__gte=date((date_today - relativedelta(months=1)).year, 12 if date_today.month == 1 else date_today.month - 1, 1), date_created__lt=date((date_today + relativedelta(months=1)).year, 1 if date_today.month == 12 else date_today.month + 1, 1)):
                    
                    #if not invoice.summary.startswith("Late Fee"):
                    invoice_line_items.append([
                        invoice.date_created,
                        invoice.date_due,
                        invoice.student,
                        invoice.summary,
                        invoice.travel_fee,
                        invoice.subtotal,
                        invoice.subtotal + invoice.travel_fee,
                        invoice.payment_status,
                    ])
                    if invoice.payment_status == Invoice.PAYMENT_STATUS_UNPAID:
                        has_unpaid_invoices = True
                    if invoice.summary == "Late Fee (%s)" % (date_today.strftime("%B"),) and invoice.date_due == date(date_today.year, date_today.month, 1):
                        late_fee_added_for_billing_period = True

                invoiced_students.append(student)
                if student.is_billing_contact and student.user.email:
                    invoice_billing_emails.append(student.user.email)

                #sending one invoice per family
                for parent in student.parents.all():
                    for student in parent.student_set.all():

                        if student not in invoiced_students:

                            #currently, email needs to print all invoice details from last month and current month
                            for invoice in student.invoice_set.filter(date_created__gte=date((date_today - relativedelta(months=1)).year, 12 if date_today.month == 1 else date_today.month - 1, 1), date_created__lt=date((date_today + relativedelta(months=1)).year, 1 if date_today.month == 12 else date_today.month + 1, 1)):

                                #if not invoice.summary.startswith("Late Fee"):
                                invoice_line_items.append([
                                    invoice.date_created,
                                    invoice.date_due,
                                    invoice.student,
                                    invoice.summary,
                                    invoice.travel_fee,
                                    invoice.subtotal,
                                    invoice.subtotal + invoice.travel_fee,
                                    invoice.payment_status,
                                ])
                                if invoice.payment_status == Invoice.PAYMENT_STATUS_UNPAID:
                                    has_unpaid_invoices = True
                                if invoice.summary == "Late Fee (%s)" % (date_today.strftime("%B"),) and invoice.date_due == date(date_today.year, date_today.month, 1):
                                    late_fee_added_for_billing_period = True

                            invoiced_students.append(student)
                            if student.is_billing_contact and student.user.email:
                                invoice_billing_emails.append(student.user.email)

                    if parent.is_billing_contact and parent.user.email:
                        invoice_billing_emails.append(parent.user.email)


                if not invoice_line_items:
                    continue
                elif has_unpaid_invoices and date_today.day == late_fee_activation_day and not late_fee_added_for_billing_period:
                    
                    #add late fee invoice to system and invoice_line_items
                    late_fee_invoice = Invoice.objects.create(
                        student=student,
                        summary="Late Fee (%s)" % (date_today.strftime("%B"),),
                        subtotal=Decimal('20.00'),
                    )

                    invoice_line_items.append([
                        late_fee_invoice.date_created,
                        late_fee_invoice.date_due,
                        late_fee_invoice.student,
                        late_fee_invoice.summary,
                        late_fee_invoice.travel_fee,
                        late_fee_invoice.subtotal,
                        late_fee_invoice.subtotal + late_fee_invoice.travel_fee,
                        late_fee_invoice.payment_status,
                    ])

                #format the email greeting
                billing_email_greeting = "Parents and Students,"
                if User.objects.filter(email__in=invoice_billing_emails).exclude(first_name__exact="-not found-").exists():
                    billing_email_greeting = ""
                    for contact in User.objects.filter(email__in=invoice_billing_emails).exclude(first_name__exact="-not found-"):
                        billing_email_greeting += "%s," % (contact.first_name,)
                    
                    billing_email_greeting = billing_email_greeting.replace(",", " and ", billing_email_greeting.count(',') - 1)
     
                #send the email now
                amount_due = Decimal('0.00')
                html_message = "<html>Hello %s<br /><br />The following is an invoice summary for all lessons billed and credited up to %s:<br /><br /><table><thead><tr><td>Invoice Date</td><td>Due Date</td><td>Student Name</td><td>Summary</td><td>Travel Fee</td><td>Subtotal</td><td>Total</td><td>Status</td></tr></thead>" % (billing_email_greeting, date_today.strftime("%A %B %-d, %Y"),)
                for line_item in sorted(invoice_line_items, key=itemgetter(0)):
                    
                    line_color = 'darkgrey'
                    if line_item[7] == Invoice.PAYMENT_STATUS_UNPAID:
                        amount_due += line_item[6]
                        line_color = 'firebrick'
                    elif line_item[7] == Invoice.PAYMENT_STATUS_PAID:
                        line_color = 'forestgreen'
                    elif line_item[7] == Invoice.PAYMENT_STATUS_CREDIT:
                        amount_due -= line_item[6]
                        line_color = 'deepskyblue'

                    html_message += "<tr style='color: %s;'><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>$%s</td><td>$%s</td><td><b>$%s</b></td><td>%s</td></tr>" % (
                        line_color,
                        line_item[0],
                        line_item[1],
                        line_item[2],
                        line_item[3],
                        line_item[4],
                        line_item[5],
                        line_item[6],
                        line_item[7],
                    )
                html_message += "<tr style='color: %s;'><td colspan='6'></td><td><b>$%s</b></td><td>AMOUNT %s</td></tr></table><br />Please reply to this email if any of the amounts above look incomplete or incorrect; late fees for unpaid invoices are processed on the 11th of every month.<br /><br />Thank you,<br /><br />-Administrator</html>" % ('deepskyblue' if amount_due < 0 else 'firebrick', amount_due if amount_due != 0 else '0.00', 'CREDITED' if amount_due < 0 else 'DUE',)

                if is_dry_run:
                    invoice_billing_emails = [os.environ['CVAR_DRY_RUN_EMAIL']]

                invoice_email = EmailMessage(subject="%s Invoice Summary" % (date_today.strftime("%B"),), body=html_message, to=invoice_billing_emails)
                invoice_email.content_subtype = "html"
                invoice_email.send(fail_silently=False)

        self.stdout.write(self.style.SUCCESS("Successfully processed all billing alerts"))