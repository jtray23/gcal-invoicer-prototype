# gcal-invoicer-prototype

A simple Django 1.11 email invoicing app (prototype) which automatically generates lessons based on specific Google Calendar events.

## License & Disclaimer

This project is licensed under the GPLv3 License (see the [LICENSE.md](LICENSE.md) file for details)

Furthermore, this is a PERSONAL PROJECT that I made for my wife because there was no app or service we could find at the time which allowed for simple invoicing based on Google calendar events (so you don't have to duplicate your schedule in a separate invoicing app). As such, it is a prototype that describes my approach to solving this problem, and would need extensive refactoring before being "released" as an open source app.

## Overview

This app is highly opinionated about how invoicing is done, and almost none of it will be applicable to your own use case (without extensive modification). However, for the sake of documentation, I have summarized specifically how this app allows us to invoice our students:

1. **Create a new calendar lesson event on your Google Calendar for the student** (only some calendar events will be lessons, not everything on the calendar, so we need to tell Django which ones are lessons).
   1. Make sure the calendar lesson event title is "First_name Last_name (child)" if this is a child student, or "First_name Last_name (adult)" if the student is an adult (this makes it possible to bill adult students in addition to single and multiple child students per parent/guardian, and still have all invoicing for separate children combined in one email for each parent/guardian).
   2. If the student is a child student, make sure the parent is in your Google Contacts (only Name + Email Address are required) and then invite that parent/guardian (or invite multiple parents/guardians, if they want to be CC'd on all invoices) to the calendar lesson event (Django will automatically detect each new parent/guardian Name and Email Address, then create their user account based on this. Additionally, a user account for the child student, if present, is created without an Email Address using the Name in the calendar event title).
   3. Make sure the calendar event lesson duration fits into the valid billable time spans (currently, 30mins/45mins/1hr/1hr30mins, all other invalid gcal event durations will be ignored by the system).
   4. Set the Recurrence of the calendar event lesson (only "Weekly until Date" and "Weekly until X occurences" is supported), so Django can create a series of lessons for this student (changing an individual lesson time later on any single event in the series is also supported, in case one lesson time needs to be moved to a new day or time).
2. **At some point in the next 10 minutes, the Heroku Scheduler will call the Django command which syncs New and Modified Google Calendar Lesson Events with Lesson and Invoice objects** (we only need to log into the system to check invoice accuracy and new students at the end of the month, not necessarily during the month).
   1. After each lesson concludes, make sure to log into Django Admin and go to the Lesson, then change it from "Planned" to "Attended" or to "Late Cancellation" (the Invoice will be "Unpaid" by default in either case), or to "Cancellation (Makeup)" (which Voids the Invoice as the lesson must be rescheduled with a makeup Lesson) or to "Cancellation (Credit)" (which Credits the Invoice as the lesson cancellation was a caused by a mistake on our behalf).
   2. If the student paid for the lesson now, go to the Invoice and change it from "Unpaid" to "Paid" (but typically we "mark as paid" in batch with Django Admin at the end of the month, because that's much easier and faster).
3. **On the 1st of every month, the Django Billing Alerts command needs to be run manually, after making sure all new students have a valid billing plan.** (I used the Heroku Scheduler add-on for this along with the command ```python manage.py syncalleventstolessons```).
   1. Run the Django Billing Alerts command after making sure the Heroku config var "Dry Run" is set to "True" (I use ```$ heroku run python manage.py processbillingalerts -a YOUR-HEROKU-APP-NAME-HERE```A Dry Run sends invoices to the Dry Run Email Address, and not the students/parents/guardians Email Addresses, so we can make sure all new students have a billing plan selected, and all extra parents that want to be CC'd are correctly CC'd).
   2. If any students have a Zero dollar invoice, that means the student still needs a billing plan selected, so find the student user (or parent/guardian user, if teaching multiple children in one large time block) and select their billing plan (currently, various flat rates and flat rates + tiered travel fees).
   3. If any other parents/guardians want to be CC'd on the monthly invoice, and you didn't invite them to the first lesson calendar event, then manually add that user account now with a name, email address, and select the student children name(s) from the list (this part should really be done above when creating the lesson event by inviting *all* billing contact parent/guardians to the lesson event, to save time) and make sure to select the "Billing Contact" checkbox, then save (all parent/guardians will get a copy of the same invoice for all children they have enrolled).
   4. After the Dry Run shows all invoice amounts, parent/guardian names, and parent/guardian email addresses are correct, change the Heroku config var "Dry Run" to "False" and run the Django command again to send out the late invoice emails.
4. **On the 10th of every month, run the Django Billing Alerts command again to process late fees and send late invoices.**
   1. If any student has any Invoice marked as "Unpaid", then a late fee will be added to the Invoice Email (use a "Dry Run" as above to make sure all paid Invoices were correctly marked as "Paid" before emailing late invoices with Dry Run set to "False").

## Setup

1. This prototype Djano app uses the wonderful [Heroku Django Template](https://github.com/heroku/heroku-django-template) so a comparable Django envirnoment needs to be set up on Heroku (and I would highly recommend starting with this template).
2. Choose a Python version (probably going to be Python3 at this point).
3. Make sure Django is configured to send emails (which can be done in various ways).
4. Make sure your GMail Account has an app password created if you want to send email out via that address (an app password **must** be created on all Gmail accounts with 2-factor authentication)
4. Create a new calendar in Google Calendar, or just use your primary one, then Find your Private Google Calendar URL (Google Calendar -> Calendar Settings & Sharing -> Secret Address in iCal format

Heroku config vars that need to be created for this app:

```term
$ heroku config
CVAR_CALENDAR:       https://calendar.google.com/calendar/ical/***********%40gmail.com/private-****************/basic.ics
CVAR_DRY_RUN:        True
CVAR_EMAIL_PASSWORD: *****************
CVAR_EMAIL_USERNAME: ************@gmail.com
DATABASE_URL:      postgres://************:*******************.compute-*.amazonaws.com:*****/*****************
CVAR_DRY_RUN_EMAIL: *********+invoiceDryRun@gmail.com
```
