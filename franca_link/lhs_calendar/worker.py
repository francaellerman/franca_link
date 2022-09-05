import pdfminer.high_level
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
import PyPDF2
import pickle
import os
import tabula
import sqlite3
import pandas as pd
import numpy as np
import pkg_resources
import subprocess
import logging
import re
import icalendar as ical
import yaml
import pytz
import datetime
import urllib.parse
import franca_link.my_logging as my_logging
import magic
import warnings
import io
import requests
import pyffx
from cryptography.fernet import Fernet
import time as time_lib

start = 'calendar/'

my_logger = my_logging.wrapper_related('franca_link.calendar')

#Functions for getting data from any PDF

#These shouldn't send an email in the end because that would be annoying
class pdf_verification_exception(Exception):
    pass

pyffx_length = 10

with open('/etc/franca_link/lhs_calendar_config.yaml', 'rb') as f:
    config_dict = yaml.safe_load(f)

with open('/etc/franca_link/lhs_calendar_fernet.txt', 'rb') as f:
    fernet = Fernet(f.read())

def format_name(name):
    comma = name.find(',')
    return name[comma + 2:] + ' ' + name[:comma]

def display_name(name, hr):
    nickname = db("select nickname from students where name = ? and hr = ?", [name, hr])[0][0]
    if nickname: name = nickname
    return format_name(name)

def look(li, item):
    try: return li.index(item)
    except ValueError: return None

def get_metadata(fp):
    #This was from some example
    parser = PDFParser(fp)
    doc = PDFDocument(parser)
    return doc.info[0]

def verify_pdf(file, time):
    global config_dict
    config = config_dict
    mime = magic.from_buffer(file.read(2048))
    if not mime == 'PDF document, version 1.4 (password protected)':
        raise pdf_verification_exception(f"Mimetype {mime} is not the required type")
    #Try to catch people trying to tamper with the files
    with warnings.catch_warnings(record=True) as caught_warnings:
        md = get_metadata(file)
        if not md.get('Producer') == b'iText 2.1.5 (by lowagie.com)':
            raise pdf_verification_exception("Metadata does not fit the criteria: same producer", md.get('Producer'))
        if not md.get('ModDate') == md.get('CreationDate'):
            my_logger.warning(f"Metadata does not fit the criteria: same mod and creation, {md.get('ModDate')}, {md.get('CreationDate')}", extra={'db_created': time, 'calendar_name': information.get('name'), 'calendar_hr': information.get('hr')})
        #today = datetime.datetime.now().astimezone(pytz.timezone('America/New_York')).strftime('%Y%m%d')
        #day = md.get('CreationDate').decode('utf-8')[2:10]
        #if not today == day:
        #    raise pdf_verification_exception(f"Uploaded PDF is from {md.get('CreationDate')}, not today")
        if len(caught_warnings) > 0:
            raise Exception("Getting PDF metadata raised a warning")
    if md.get('Creator') == b'JasperReports (StudentScheduleHighSchool)':
        teacher = False
    elif md.get('Creator') == b'JasperReports (TeacherScheduleHighSchool)':
        teacher =  True
    else:
        raise pdf_verification_exception("Metadata does not fit the criteria: same creator", md.get('Creator'))
    first_year = str(config['semester_periods'][0][0])
    if teacher: title = "LEXINGTON HIGH SCHOOL STAFF SCHEDULE FOR "
    else: title = "LEXINGTON HIGH SCHOOL SCHEDULE FOR "
    file_first_year = between(get_pdf_text(time),title ,"-")
    if not file_first_year == first_year:
        raise pdf_verification_exception("First year in title is", file_first_year)
    return teacher

def get_pdf_text(time):
    #output_string = io.StringIO()
    #pdfminer.high_level.extract_text_to_fp(f, output_string)
    #string = output_string.getvalue()
    #print(string)
    #return string
    return pdfminer.high_level.extract_text(start + 'pdfs/' + time + '.pdf')

def between(base, str1, str2):
    start = base.find(str1) + len(str1)
    #So that str2 has to be after str1
    return base[start:base.find(str2, start)]

def get_pdf_info(time, teacher):
    info = {}
    text = get_pdf_text(time)
    #info['name'] = between(text, '', '\n')
    comma = text.find(',')
    start = text.rfind('\n',0,comma) + 1
    end = text.find('\n', comma, -1)
    info['name'] = text[start:end]
    if teacher:
        info['hr'] = between(text, 'Adv-', '\n\n')
    else:
        info['hr'] = between(text, 'HR:\n\n', '\n')
    return info

def db(*args, no_Row=False, file='calendar.sql'):
    con = sqlite3.connect(start + file)
    if not no_Row:
        con.row_factory = sqlite3.Row
    cur = con.cursor()
    try:
        resp = cur.execute(*args).fetchall()
        con.commit()
        con.close()
        return resp
    except Exception as e:
        con.close()
        raise e

def delete_previous_rows(information):
    db("delete from enrollments where student_name = ? and student_hr = ?", [information['name'], int(information['hr'])])
    #if list(cur.execute(
    #    "select name from students where id = ?", [id_])):
    #    cur.execute("delete from students where id = ?", [id_])
    #    cur.execute("delete from enrollments where student_id = ?", [id_])
    #    return True
    #return False

def insert_sql_data(information, time, file, teacher, local=False):
    assert not information['name'].find(',') == -1
    if teacher: df = teacher_table(get_pdf_text(time))
    else:
        df = tabula.read_pdf(file, pages=1, silent=True)[0]
        separate_df(df)
    insert_df_in_sql(information, time, df, local=local)

def is_Course(text):
    hyphen = text.find('-')
    try:
        if hyphen == -1: raise ValueError
        else: int(text[hyphen + 1:])
    except ValueError: return False
    else: return True

def teacher_table(text):
    df = pd.DataFrame()
    stop = text.find('\n\nLEXINGTON HIGH SCHOOL STAFF SCHEDULE FOR ')
    if stop == -1: stop = len(text)
    cells = text[:stop].split('\n\n')
    Course_start = None
    for index, value in enumerate(cells):
        if not Course_start and is_Course(value):
            Course_start = index
        elif Course_start and not is_Course(value):
            Course_end = index
            break
    cells = cells[Course_start:]
    length = Course_end - Course_start
    column_names = ['Course', 'Description', 'Room', 'Term', 'Schedule']
    if not len(cells) == length * len(column_names): raise Exception("Columns are not the required length")
    for index, name in enumerate(column_names):
        df[name] = cells[index*length:(index+1)*length]
    df['Level'] = None
    df['Teacher'] = None
    return df

def separate_df(df):
    closies = [['Teacher', 'Term']]
    def teacher_room(value):
        return [value[:-3 - 1], value[-3:]]
    def separate_col(closie, col):
        nonlocal closies
        df[closies[closie][0]] = df[col].apply(lambda value: value[:-3 -1])
        df[closies[closie][1]] = df[col].apply(lambda value: value[-3:])
    def check_separate_col(col):
        nonlocal closies
        for closie in range(1):
            if closies[closie][0] in col and closies[closie][1] in col:
                separate_col(closie, col)
    [check_separate_col(col) for col in df.columns]

def insert_df_in_sql(information, time, df, local=False):
    df = df[['Course','Level','Description', 'Room','Teacher','Term','Schedule']]
    df = df.replace('', np.nan)
    df = df.dropna(axis=0, subset=['Description', 'Course', 'Term', 'Schedule'])
    df = df.replace({np.nan: None})
    def correct_format(row):
        boolean = (bool(re.match('^(?:[A-H][1-4]*)+$', row['Schedule'])) and
                not row['Course'].find('-') == -1)
        return boolean
    include = df.apply(correct_format, axis=1)
    df = df.loc[include]
    def trim_teacher(value):
        if type(value) == str:
            found = value.find(';')
            if found == -1: return value
            else: return value[:found]
        else: return None
    df['Teacher'] = df['Teacher'].apply(trim_teacher)
    delete_previous_rows(information)
    db("insert into students(name, hr, created, privacy, lock) values(?,?,?,?,?) on conflict(name, hr) do update set created = excluded.created, lock = excluded.lock", [information['name'], information['hr'], time, 'Default', 1])
    #empty cells are outputted as nans. dropnan deletes rows with nans like
    #counselor seminars and I-block
    #No one cares about credits
    df['student_name'] = information['name']
    df['student_hr'] = int(information['hr'])
    df['created'] = time
    def split_course(row):
        middle = row['Course'].find('-')
        course_no = row['Course'][:middle]
        section = int(row['Course'][middle + 1:])
        return pd.Series([course_no, section], index=['course_no', 'section'])
    df = pd.concat([df, df.apply(split_course, axis=1)], axis=1, join='inner')
    #Shouldn't be a necessary line but just in case I'm wrong
    df = df[df['course_no'] != 'Iblock']
    def collect_class_info(name, primary_keys, cols, created):
        course_df = df[primary_keys + cols]
        if name == 'courses':
            primary_keys[0] = 'id'
        insert_string = f"insert into {name}({','.join(primary_keys + cols)},created) values({','.join(['?']*(len(primary_keys + cols)+1))})"
        def make_equal(name):
            #is allows nulls to also be compared while = does not
            return f"{name} is ?"
        primary_keys_same = ' and '.join([make_equal(x) for x in primary_keys])
        exists_string = f"select {','.join(cols)} from {name} where {primary_keys_same}"
        def upsert_course_name(primary_key_values, row):
            global my_logger
            updated = False
            current_sql_row_list = db(exists_string,primary_key_values)
            if len(current_sql_row_list) == 0:
                #Means that nothing has its unique IDs so I can insert
                db(insert_string, primary_key_values + row + [created])
            elif config_dict['allow_updates']:
                for index in range(len(cols)):
                    if not row[index] == None and not row[index] == current_sql_row_list[0][cols[index]]:
                        updated = True
                        db(f"update {name} set {cols[index]} = ?  where {primary_keys_same}", [row[index]] + primary_key_values)
                        warning = f'SQL row {primary_key_values} was updated with {row[index]}'
                        if local: print(warning)
                        if not local: my_logger.warning(warning, extra={'calendar_name': information['name'], 'calendar_hr': information['hr'], 'db_created': time})
                if updated: db(f"update {name} set created = ? where {primary_keys_same}", [created] + primary_key_values)
        #Rows will be in order of cols
        [upsert_course_name(list(row[:len(primary_keys)]), list(row[len(primary_keys):])) for row in course_df.to_numpy()]
    #First items in cols must be the primary key
    collect_class_info('courses', ['course_no'], ['Description', 'Level'], time)
    collect_class_info('sections', ['course_no', 'Term', 'section'], ['Room', 'Teacher', 'Schedule'], time)
    con = sqlite3.connect(start + 'calendar.sql')
    try:
        df[['created', 'student_name', 'student_hr', 'course_no', 'section', 'Term']].to_sql(
            'enrollments', con=con, if_exists='append', index=False)
        con.close()
    except Exception as e:
        con.close()
        raise e
    db("update students set lock = 0 where name = ? and hr = ?",
            [information['name'], information['hr']])

def process_db_created(time):
    file = open(f'{start}pdfs/{time}.pdf', 'rb')
    return process_pdf(file, time, local=True)

def process_pdf(file, time, local=False):
    global config_dict
    file.seek(0)
    teacher = verify_pdf(file, time)
    file.seek(0)
    information = get_pdf_info(time, teacher)
    if information['name'] in config_dict['banned_names']:
        raise Exception(f"{information['name']} is banned")
    #if worker.returning_user_name(information['ID']):
    #    message = "Request success: returning user"
    file.seek(0)
    insert_sql_data(information, time, file, teacher, local=local)
    return information

def make_class_variables(cls):
    #Because no one wants to deal with Python's class scoping
    global config_dict
    cls.config = config_dict
    cls.tz = pytz.timezone('America/New_York')
    def make_date(tup):
        return datetime.datetime(*tup, tzinfo = pytz.timezone('America/New_York'))
    cls.semester_periods = {'S 1': None, 'S 2': None}
    for index, semester in enumerate(cls.semester_periods):
        cls.semester_periods[semester] = [make_date(cls.config['semester_periods'][i])
                for i in [index, index + 1]]
        #def get_date(key, d='semester_periods'):
        #    nonlocal make_date
        #    return make_date(config_dict[d][key])
    cls.all_cs_dates = {k: [make_date(tup) for tup in v] for k, v in cls.config['cs_dates'].items()}
    cls.quarter_turnovers = {}
    for semester in cls.semester_periods:
        cls.quarter_turnovers[semester] = make_date(cls.config['quarter_turnovers'][semester])

class LHS_Calendar:

    def __init__(self, name, hr, just_lunch=False):
        self.just_lunch = just_lunch
        while True:
            lock = db("select lock from students where name = ? and hr = ?", [name, 
                hr])[0]['lock']
            if lock == 1: time_lib.sleep(.5)
            elif lock == 0: break
        self.hr = hr
        while True:
            try:
                with open(start + 'calendar.ics', 'rb') as f:
                    self.cal = pickle.load(f)
                break
            except FileNotFoundError:
                continue
        self.datetime = datetime.datetime.utcnow()
        self.time_ = self.datetime.strftime('%Y%m%dT%H%M%SZ')
        event = ical.Event()
        event['summary'] = self.time_
        event['last-modified'] = self.time_
        event['dtstart'] = '20220630T000000Z'
        event['dtend'] = '20220630T240000Z'
        self.cal.add_component(event)
        tz = Find_and_replace.tz(self.cal)
        self.blocks = {"S 1": {}, "S 2": {}}
        self.lunches = {"S 1": [None]*6, "S 2": [None]*6}
        ex = db("select course_no, description, level, term, room, teacher, schedule from enrollments join courses on enrollments.course_no = courses.id join sections using(course_no, section, term) where student_name = ? and student_hr = ?", [name, hr])
        assert len(ex) > 0
        self.cs_block = None
        [self.make_block(row) for row in ex]
        if just_lunch: return
        self.cal['X-WR-CALNAME'] = f"Quickly: {display_name(name, hr)}'s calendar"
        self.cal['X-WR-CALDESC'] = "Updates every 24 to 48 hours. Go to http://franca.link/quickly to see information on your calendar."
        self.dates_to_lunches = {'S 1':{}, 'S 2':{}}
        #For people who might not have a Counselor Seminar so special_edit_event
        #doesn't fail to recognize self.cs_block
        [[[self.edit_event(func, semester, subcomponent) for subcomponent in
                self.cal.subcomponents]
                for func in [LHS_Calendar.special_edit_event,
                            LHS_Calendar.edit_lunches_of_day,
                            LHS_Calendar.delete_other_lunches,
                            ]]
                for semester in LHS_Calendar.semester_periods]
        self.del_empty_subcomponents()
        self.ical = self.cal.to_ical().decode('utf-8')
    
    def get_datetime(event):
        time = ical.prop.vDDDTypes.from_ical(event['DTSTART'])
        if type(time) is datetime.date:
            time = Find_and_replace.date_to_datetime(LHS_Calendar.tz, time)
        return time

    def make_block(self, row):
        if row['course_no'].startswith('CS'):
            self.cs_block = row['Schedule']
            grade = int(row['course_no'][2:])
            self.cs_dates = LHS_Calendar.all_cs_dates[grade]
            self.cs_room = row['Room']
        else:
            terms = []
            #It seems to remember the capitalization of each column??
            #ex. course_no and Term
            row = dict(row)
            if row['Term'] == 'ALL':
                for term in self.blocks:
                    terms.append(term)
            elif row['Term'] in self.blocks:
                terms.append(row['Term'])
            match_objects = re.finditer(LHS_Calendar.config['re_pattern'], row['Schedule'])
            rest_of_row = row.copy()
            rest_of_row.pop('Term')
            rest_of_row.pop('Schedule')
            for match_object in match_objects:
                letter = match_object.group('letter')
                numbers = match_object.group('number')
                if numbers == '':
                    #Ex. if the block of a class is listed as "A,"
                    #then it's equivalent to "A1234"
                    numbers = '1234'
                for number in numbers: #
                    for term in terms:
                        if not self.just_lunch: self.blocks[term][letter + number] = rest_of_row
                        self.make_lunch(row, term, letter + number)

    def make_lunch(self, row, term, block):
        day = look(LHS_Calendar.config['lunch_blocks'], block)
        if day is not None:
            course_no = row['course_no']
            if re.match(LHS_Calendar.config['first_lunch'], course_no):
                self.lunches[term][day] = 0
            #Gym is covered by first lunch so room should be a number from here on
            #If row['Room'] is None then I can't determine lunch so I'll just
            #let all three be displayed
            elif row['Room'] is not None:
                room = int(row['Room'])
                if room % 2 == 0: self.lunches[term][day] = 1
                elif room % 2 == 1: self.lunches[term][day] = 2
                else: raise Exception(row, block, "does not fit criteria for any lunches")

    def edit_event(self, func, semester, subcomponent):
        if (type(subcomponent) is ical.cal.Event
            and not subcomponent.is_empty()):
            time = LHS_Calendar.get_datetime(subcomponent)
            #If period is None, the period is assumed to be always
            if semester is None or (time >= LHS_Calendar.semester_periods[semester][0]
                and time < LHS_Calendar.semester_periods[semester][1]):
                subcomponent['LAST-MODIFIED'] = self.time_
                func(self, semester, subcomponent)

    def special_edit_event(self, semester, event):
        #SUMMARY is the title of the event
        #If SUMMARY is in replacements, SUMMARY is changed to that
        #key's corresponding value (the first parameter), otherwise
        #it is changed to SUMMARY itself (second paramter).
        value = self.blocks[semester].get(event['SUMMARY'])
        time_ = LHS_Calendar.get_datetime(event)
        if event['SUMMARY'] == 'Advisory':
            event['location'] = str(self.hr)
        elif (event['SUMMARY'] == self.cs_block
            and time_ >= self.cs_dates[0] and time_ <= self.cs_dates[1]):
            event['summary'] = f'Counselor Seminar ({self.cs_block})'
            if self.cs_room: event['location'] = self.cs_room
        elif value is not None:
            event['SUMMARY'] = f'{value["Description"]} ({event["SUMMARY"]})'
            #def place_for(key, newline = True):
            #    nonlocal value
            #    if key == 'Teacher': 
            #    if value[key] is not None: return value[key] + '\n'
            #    else: return ''
            if value['Level']: event['description'] += value['Level'] + '\n'
            if value['Teacher']: event['description'] += format_name(
                    value['Teacher']) + '\n'
            #event['DESCRIPTION'] = place_for("Level") + place_for("Teacher")
            if value['Room'] is not None: event['LOCATION'] = value['Room']
        local_time = self.datetime.replace(tzinfo=pytz.utc).astimezone(LHS_Calendar.tz)
        user_time = local_time.strftime('%a, %b %d, %Y at %I:%M %p')
        event['description'] += 'Google Calendar last updated your calendar ' + user_time
        #I'm not doing the following code because people might want to still
        #know the times of the three lunches to see their friends or smth
        #elif event['SUMMARY'] in LHS_Calendar.config['lunch_blocks']:
        #    event['SUMMARY'] = f'{event["SUMMARY"]} (Lunch)'

    def edit_lunches_of_day(self, semester, event):
        #See if the event is a 'Day #' event.
        day_res = re.match(LHS_Calendar.config['day_pattern'], event['SUMMARY'])
        if day_res:
            #The lunches are stored starting at 0 while Days start at 1
            #This will return a 0, 1, or 2
            lunch_no = self.lunches[semester][int(day_res.group(1)) - 1]
            time_ = LHS_Calendar.get_datetime(event)
            if time_ >= LHS_Calendar.quarter_turnovers[semester]:
                if lunch_no == 1: lunch_no = 2
                elif lunch_no == 2: lunch_no = 1
            #If I didn't do copy(), lunches would be removed
            #directly from self.lunches
            other_lunches = LHS_Calendar.config['all_lunches'].copy()
            if lunch_no is None: other_lunches = []
            else: other_lunches.pop(lunch_no)
            date = ical.prop.vDDDTypes.from_ical(event['DTSTART'])
            if type(date) is not datetime.date:
                raise Exception("This Day # event is not an all-day event")
            self.dates_to_lunches[semester][(date)] = other_lunches

    def delete_other_lunches(self, semester, event):
        event_datetime = ical.prop.vDDDTypes.from_ical(event['DTSTART'])
        if type(event_datetime) == datetime.datetime:
            date_dict = self.dates_to_lunches[semester]
            date_key = (event_datetime.date())
            lunches = date_dict.get(date_key)
            #If there are lunches on this date, delete this if it's a lunch.
            if lunches is not None and event['SUMMARY'] in lunches:
                #Deletes everything inside, but not itself. See documentation.
                event.clear()

    def del_empty_subcomponents(self):
        empty_event = ical.cal.Event()
        while True:
            try:
                self.cal.subcomponents.remove(empty_event)
            except ValueError:
                return

make_class_variables(LHS_Calendar)

class Find_and_replace:
    def date_to_datetime(tz, date):
        return datetime.datetime.combine(date,
                                         datetime.datetime.min.time(),
                                         tzinfo = tz)

    def tz(cal):
        return pytz.timezone(cal['X-WR-TIMEZONE'])

    def edit_event(replacements, event):
        #SUMMARY is the title of the event
        #If SUMMARY is in replacements, SUMMARY is changed to that
        #key's corresponding value (the first parameter), otherwise
        #it is changed to SUMMARY itself (second paramter).
        event['SUMMARY'] = replacements.get(event['SUMMARY'],
                                            event['SUMMARY'])

    #def find_and_replace(args, cal, period=None):
    #    find_and(Find_and_replace.edit_event, **locals())

    def find_and(func, func_args, cal, period=None):
        tz = Find_and_replace.tz(cal)
        subs = cal.subcomponents
        for subcomponent in cal.subcomponents:
            #Must be an Event because there's a timezone subcomponent
            #When edit_lunches_of_day comes back again after
            #delete_other_lunches cleared a lunch, those cleared events should
            #be ignored.
            if (type(subcomponent) is ical.cal.Event
                and not subcomponent.is_empty()):
                time = ical.prop.vDDDTypes.from_ical(subcomponent['DTSTART'])
                if type(time) is datetime.date:
                    time = Find_and_replace.date_to_datetime(tz, time)
                #If period is None, the period is assumed to be always
                if not period or (time >= period[0] and time < period[1]):
                    func(*func_args, subcomponent)

def make_ics_query_string(information):
    global fernet
    def make_query(data):
        return urllib.parse.quote_plus(fernet.encrypt(data).decode())
    return f"?0={urllib.parse.quote_plus(information['name'])}&2={make_query(int(information['hr']).to_bytes(2, byteorder='big'))}"

def ffx_key():
    return str.encode(config_dict['ffx_secret_key'])

def old_make_ics_query_string(information):
    hr = int(information['hr'])
    enc = pyffx.Integer(ffx_key(), length=pyffx_length).encrypt(hr)
    enco_hr = urllib.parse.quote_plus(str(enc))
    return f"?0={urllib.parse.quote_plus(information['name'])}&1={enco_hr}"

def get_user_calendar(name, version, enc_hr):
    #Flask should have already decoded the strings before this function
    #I'm a little concerned about using urllib to encode the queries but letting
    #Flask decode the queries since they could do it differently
    if version == '1':
        hr = pyffx.Integer(ffx_key(), length=pyffx_length).decrypt(int(enc_hr))
    elif version == '2':
        def decode_query(string):
            return fernet.decrypt(str.encode(string))
        hr = int.from_bytes(decode_query(enc_hr), 'big')
    return LHS_Calendar(name, hr).ical

def get_connections(information):
    classes = db('select course_no, section, term from enrollments where student_name = ? and student_hr = ?', [information['name'], information['hr']], no_Row=True)
    course_select = "select student_name, student_hr from enrollments where not (student_name == ? and student_hr = ?) and course_no = ? and section = ? and term = ?" 
    classmates = {class_: db(course_select, (information['name'],information['hr']) + class_, no_Row=True)
            for class_ in classes}
    def names(l):
        return [display_name(*tuple_of_name) for tuple_of_name in l]
    classmates = {k: names(v) for k, v in classmates.items()}
    def get_coursename(no):
        return db("select description from courses where id = ?", [no], no_Row=True)[0][0]
    classmates = [
            {'class':
                {'course': get_coursename(k[0]), 'section': k[1], 'term': k[2]},
            'classmates': v}
            for k, v in classmates.items() if len(v) > 0] #restrict to full classes
    return classmates

#Functions for getting the initial data, only used once

def load_metadata(filename):
    with open("pdf_metadata.pickle", 'wb') as f:
        pickle.dump(get_metadata(open(filename, 'rb')), f)

def load_info_finder_text(filename):
    with open(filename, 'rb') as f:
        text = get_pdf_text(f)
    name = 'Ellerman, Franca'
    hr = '225'
    finders = [text[:text.find(name)],
        between(text, name, hr),
        '\n']
    with open('pdf_info_finders.pickle', 'wb') as f:
        pickle.dump(finders, f)

def load_official_calendar():
    url = 'https://calendar.google.com/calendar/ical/lexingtonma.org_qud45cvitftvgc317tsd2vqctg%40group.calendar.google.com/public/basic.ics'
    response = requests.get(url).text
    with open(start + 'new_calendar.ics', 'wb') as f:
        pickle.dump(ical.Calendar.from_ical(response), f)
    #I don't _think_ I need delete old_calendar.ics?
    os.rename(start + 'calendar.ics', start + 'old_calendar.ics')
    os.rename(start + 'new_calendar.ics', start + 'calendar.ics')

def make_sql_databases():
    con = sqlite3.connect(start + "calendar.sql")
    cursor = con.cursor()
    #It's unclear if the sections are unique to each term or not
    #This isn't autoincrement for a reason I can't remember
    cursor.execute("create table students(name text, hr int, created text, nickname text, privacy text, lock int, primary key (name, hr))")
    cursor.execute("create table courses(id text primary key, created text, Description text, Level text)")
    cursor.execute("create table sections(course_no text, Term text, section int, created text, Room text, Teacher text, Schedule text, primary key (course_no, Term, section), foreign key(course_no) references courses(id))")
    cursor.execute("create table enrollments(id integer primary key, created text, student_name text, student_hr int, course_no text, section int, Term text, foreign key (course_no, section, Term) references sections (course_no, section, Term))")
    #Since I can't see students' IDs I don't need to store anything
    #cursor.execute("create table students(id integer primary key, created text, HR int, name text)")
    con.commit()
    con.close()
