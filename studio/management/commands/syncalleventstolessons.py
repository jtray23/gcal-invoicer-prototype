from django.core.management.base import BaseCommand, CommandError
from studio.models import Parent, Student, Lesson

from django.contrib.auth.models import User, Group
from icalendar import Calendar
from datetime import timedelta
from pytz import timezone
import requests
import os

class Command(BaseCommand):
    help = 'Syncs all events from specifed gcal to lessons objects'

    def handle(self, *args, **options):

        vevent_uid_list = []
        gcal = Calendar.from_ical(requests.get(os.environ['CVAR_CALENDAR']).text)
        for event in gcal.walk('VEVENT'):
            vevent_uid_list.append(event.decoded('UID'))

            if not event.decoded('SUMMARY') or event.decoded('SUMMARY').split()[-1].lower() not in ['(child)', '(adult)']:
                continue #not a Lesson event, skip to next Calendar event

            duration = event.decoded('DTEND').astimezone(timezone('UTC')) - event.decoded('DTSTART').astimezone(timezone('UTC'))
            if duration.seconds == 1800:
                duration = Lesson.DURATION_30_MINUTES
            elif duration.seconds == 2700:
                duration = Lesson.DURATION_45_MINUTES
            elif duration.seconds == 3600:
                duration = Lesson.DURATION_1_HOUR
            elif duration.seconds == 5400:
                duration = Lesson.DURATION_1_HOUR_30_MINUTES
            else:
                #only need to bill on the above lesson durations, add or change as needed
                continue

            #for some reason, icalendar does not find the names, so we DO IT OURSELVES!
            if 'ATTENDEE' not in event:
                self.stdout.write(self.style.NOTICE("No ATTENDEE found for lesson: %s %s (EVENT WILL BE SKIPPED)" % (event.decoded('SUMMARY'), event.decoded('DTSTART'),)))
                continue

            vevent_detected_names = []
            for line in event.to_ical().splitlines():
                if line.startswith('ATTENDEE;'):
                    fname = "-not found-"
                    lname = "-not found-"
                    if 'CN="' in line and not '@' in line.split('"')[1]:
                        name = line.split('"')[1]
                        fname = " ".join(name.split(' ')[0:-1])
                        lname = name.split(' ')[-1]
                    vevent_detected_names.append([fname, lname])

            #QUIRK WITH ICALENDAR, ATTENDEE LIST IS NOT ALWAYS A LIST
            attendee_list = event.decoded('ATTENDEE')
            if not isinstance(event.decoded('ATTENDEE'), list):
                attendee_list = [event.decoded('ATTENDEE')]

            student = None
            for attendee in attendee_list:
                detected_name = vevent_detected_names.pop(0)

                if attendee != event.decoded('ORGANIZER'):
                    
                    attendee_email = attendee.replace('mailto:', '')
                    summary_student_first_name = event.decoded('SUMMARY').split()[0]
                    summary_student_last_name = event.decoded('SUMMARY').split()[1]
                    summary_student_age_indicator = event.decoded('SUMMARY').split()[-1].lower() # (child) or (adult)
                    if Student.objects.filter(user__email=attendee_email).exists():
                        #attendee is now student
                        student = Student.objects.get(user__email=attendee_email)
                    elif Parent.objects.filter(user__email=attendee_email).exists():

                        #get name of student
                        #summary_student_first_name = event.decoded('SUMMARY').split()[0] 
                        if Student.objects.filter(parents=Parent.objects.get(user__email=attendee_email), user__first_name=summary_student_first_name).exists():

                            #student matched the first name in summary line
                            student = Student.objects.get(parents=Parent.objects.get(user__email=attendee_email), user__first_name=summary_student_first_name)
                        else:
                            #create student with name
                            #summary_student_last_name = event.decoded('SUMMARY').split()[1] 

                            new_user_student = User.objects.create_user(
                                username="%s-%s-childstudent" % (summary_student_first_name, summary_student_last_name),
                                first_name=summary_student_first_name,
                                last_name=summary_student_last_name,
                            )
                            student = Student.objects.get(user=new_user_student)
                            student.parents.add(Parent.objects.get(user__email=attendee_email))
                            student.save()

                    elif Student.objects.filter(user__first_name=summary_student_first_name, user__last_name=summary_student_last_name).exists():

                        student = Student.objects.get(user__first_name=summary_student_first_name, user__last_name=summary_student_last_name)

                    elif summary_student_age_indicator == '(child)':

                        #create both Student and Parent
                        new_user_parent = User.objects.create_user(
                            username=attendee_email.split('@')[0],
                            email=attendee_email,
                            first_name=detected_name[0],
                            last_name=detected_name[1],
                        )
                        parents_group = Group.objects.get(name='Parents')
                        new_user_parent.groups.add(parents_group)
                        new_user_parent.save()
                        #parent = Parent.objects.get(user=new_user_parent)

                        new_user_student = User.objects.create_user(
                            username="%s-%s-childstudent" % (summary_student_first_name, summary_student_last_name),
                            first_name=summary_student_first_name,
                            last_name=summary_student_last_name,
                        )
                        student = Student.objects.get(user=new_user_student)
                        student.parents.add(Parent.objects.get(user=new_user_parent))
                        student.save()

                    else:

                        #create new_user with all details for a Student record
                        new_user_student = User.objects.create_user(
                            username=attendee_email.split('@')[0],
                            email=attendee_email,
                            first_name=summary_student_first_name,
                            last_name=summary_student_last_name,
                        )
                        student = Student.objects.get(user=new_user_student)

            if not student:
                continue

            #check if event UID also has RECURRENCE-ID
            is_sequence_incremented = False
            if 'RECURRENCE-ID' in event:
                if Lesson.objects.filter(gcal_vevent_uid=event.decoded('UID'), gcal_vevent_recurrence_id=event.decoded('RECURRENCE-ID').astimezone(timezone('UTC'))).exists():
                    if Lesson.objects.filter(gcal_vevent_uid=event.decoded('UID'), gcal_vevent_recurrence_id=event.decoded('RECURRENCE-ID').astimezone(timezone('UTC'))).first().gcal_vevent_sequence != event.decoded('SEQUENCE'):
                        #delete all these events
                        Lesson.objects.filter(gcal_vevent_uid=event.decoded('UID'), gcal_vevent_recurrence_id=event.decoded('RECURRENCE-ID').astimezone(timezone('UTC'))).delete()
                        #(re)create FIRST event
                        Lesson.objects.create(
                            student=student,
                            summary=event.decoded('SUMMARY').replace(' (child)', '').replace(' (adult)', ''),
                            time_start=event.decoded('DTSTART').astimezone(timezone('UTC')),
                            duration=duration,
                            gcal_vevent_uid=event.decoded('UID'),
                            gcal_vevent_recurrence_id=event.decoded('RECURRENCE-ID').astimezone(timezone('UTC')),
                            gcal_vevent_sequence=event.decoded('SEQUENCE'),
                        )
                        is_sequence_incremented = True

                else:
                    #first remove the old version of event
                    Lesson.objects.filter(time_start=event.decoded('RECURRENCE-ID').astimezone(timezone('UTC')), gcal_vevent_uid=event.decoded('UID')).delete()

                    #create lesson and also list of recurrence
                    Lesson.objects.create(
                        student=student,
                        summary=event.decoded('SUMMARY').replace(' (child)', '').replace(' (adult)', ''),
                        time_start=event.decoded('DTSTART').astimezone(timezone('UTC')),
                        duration=duration,
                        gcal_vevent_uid=event.decoded('UID'),
                        gcal_vevent_recurrence_id=event.decoded('RECURRENCE-ID').astimezone(timezone('UTC')),
                        gcal_vevent_sequence=event.decoded('SEQUENCE'),
                    )
                    is_sequence_incremented = True

            #handle normal event UID
            elif Lesson.objects.filter(gcal_vevent_uid=event.decoded('UID')).exists():
                if Lesson.objects.filter(gcal_vevent_uid=event.decoded('UID')).first().gcal_vevent_sequence != event.decoded('SEQUENCE'):
                    #delete all these events
                    Lesson.objects.filter(gcal_vevent_uid=event.decoded('UID')).delete()
                    #Lesson.create(all necessary details from event)
                    Lesson.objects.create(
                        student=student,
                        summary=event.decoded('SUMMARY').replace(' (child)', '').replace(' (adult)', ''),
                        time_start=event.decoded('DTSTART').astimezone(timezone('UTC')),
                        duration=duration,
                        gcal_vevent_uid=event.decoded('UID'),
                        gcal_vevent_sequence=event.decoded('SEQUENCE'),
                    )
                    is_sequence_incremented = True

            #initial creation of Lesson with UID
            else:
                #create lesson and also list of recurrence
                Lesson.objects.create(
                    student=student,
                    summary=event.decoded('SUMMARY').replace(' (child)', '').replace(' (adult)', ''),
                    time_start=event.decoded('DTSTART').astimezone(timezone('UTC')),
                    duration=duration,
                    gcal_vevent_uid=event.decoded('UID'),
                    gcal_vevent_sequence=event.decoded('SEQUENCE'),
                )
                is_sequence_incremented = True

            # create recurring Lessons (if sequence update or initital creation)
            if is_sequence_incremented and 'RRULE' in event:
                if event.decoded('RRULE')['FREQ'] == ['WEEKLY']:
                    if 'UNTIL' in event.decoded('RRULE'):

                        recurrence_time_start = event.decoded('DTSTART').astimezone(timezone('UTC'))
                        while recurrence_time_start + timedelta(days=7) <= event.decoded('RRULE')['UNTIL'][0].astimezone(timezone('UTC')):

                            recurrence_time_start += timedelta(days=7)
                            Lesson.objects.create(
                                student=student,
                                summary=event.decoded('SUMMARY').replace(' (child)', '').replace(' (adult)', ''),
                                time_start=recurrence_time_start,
                                duration=duration,
                                gcal_vevent_uid=event.decoded('UID'),
                                gcal_vevent_recurrence_id=event.decoded('RECURRENCE-ID').astimezone(timezone('UTC')) if 'RECURRENCE-ID' in event else None,
                                gcal_vevent_sequence=event.decoded('SEQUENCE'),
                            )

                    elif 'COUNT' in event.decoded('RRULE'):
                  
                        count = 1
                        recurrence_time_start = event.decoded('DTSTART').astimezone(timezone('UTC'))
                        while count < event.decoded('RRULE')['COUNT'][0]:
                            count += 1
                            recurrence_time_start += timedelta(days=7)
                            Lesson.objects.create(
                                student=student,
                                summary=event.decoded('SUMMARY').replace(' (child)', '').replace(' (adult)', ''),
                                time_start=recurrence_time_start,
                                duration=duration,
                                gcal_vevent_uid=event.decoded('UID'),
                                gcal_vevent_recurrence_id=event.decoded('RECURRENCE-ID').astimezone(timezone('UTC')) if 'RECURRENCE-ID' in event else None,
                                gcal_vevent_sequence=event.decoded('SEQUENCE'),
                            )

        #delete all Lessons not existing in gcal anymore
        for lesson in Lesson.objects.all():
            if lesson.gcal_vevent_uid not in vevent_uid_list:
                Lesson.objects.filter(gcal_vevent_uid=lesson.gcal_vevent_uid).delete()

        self.stdout.write(self.style.SUCCESS("Successfully synchronized gcal Events to Lessons"))
