import pdfminer.high_level
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
import PyPDF2
import pickle
import os
import tabula
import sqlite3
import pandas as pd
import pkg_resources
import subprocess
import logging
import re
import icalendar as ical
import yaml
import pytz
import datetime
from cryptography.fernet import Fernet
import urllib.parse
import franca_link.my_logging as my_logging
import magic
import warnings
import io
import requests

start = 'calendar/'

my_logger = my_logging.wrapper_related('franca_link.calendar')

#Functions for getting data from any PDF

#These shouldn't send an email in the end because that would be annoying
class pdf_verification_exception(Exception):
    pass

with open('/etc/franca_link/lhs_calendar_config.yaml', 'rb') as f:
    config_dict = yaml.safe_load(f)

def format_name(name):
    comma = name.find(',')
    return name[comma + 2:] + ' ' + name[:comma]

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
        with pkg_resources.resource_stream('franca_link.lhs_connections', 'pdf_metadata.pickle') as f:
            franca_md = pickle.load(f)
        if not md['ModDate'] == md['CreationDate']:
            my_logger.warning("Metadata does not fit the criteria: same mod and creation", md['ModDate'], md['CreationDate'])
        if not md['Creator'] == b'JasperReports (StudentScheduleHighSchool)':
            raise pdf_verification_exception("Metadata does not fit the criteria: same creator", md['Creator'])
        if not md['Producer'] == b'iText 2.1.5 (by lowagie.com)':
            raise pdf_verification_exception("Metadata does not fit the criteria: same producer", md['Producer'], franca_md['Producer'])
        if len(caught_warnings) > 0:
            raise Exception("Getting PDF metadata raised a warning")
    first_year = str(config['semester_periods'][0][0])
    file_first_year = between(get_pdf_text(time), "LEXINGTON HIGH SCHOOL SCHEDULE FOR ","-")
    if not file_first_year == first_year:
        raise pdf_verification_exception("First year in title is", file_first_year)

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

def get_pdf_info(time):
    info = {}
    text = get_pdf_text(time)
    info['name'] = between(text, '', '\n')
    info['hr'] = between(text, 'HR:\n\n', '\n')
    return info

def db(*args, **kwargs):
    con = sqlite3.connect(start + 'calendar.sql')
    cur = con.cursor()
    try:
        resp = cur.execute(*args, **kwargs).fetchall()
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

def insert_sql_data(information, time, file):
    delete_previous_rows(information)
    db("insert into students(name, hr) values(?,?) on conflict(name, hr) do nothing", [information['name'], information['hr']])
    #cur.execute("insert into students(id, created, name) values(?,?,?)", [int(information['ID']), time, information['name']])
    #empty cells are outputted as nans. dropnan deletes rows with nans like
    #counselor seminars and I-block
    #No one cares about credits
    df = tabula.read_pdf(file,
            pages=1)[0].dropna()[['Course','Level','Description', 'Room','Teacher','Term','Schedule']]
    df['student_name'] =information['name']
    df['student_hr'] = int(information['hr'])
    df['created'] = time
    def split_course(row):
        middle = row['Course'].find('-')
        course_no = row['Course'][:middle]
        section = int(row['Course'][middle + 1:])
        return pd.Series([course_no, section], index=['course_no', 'section'])
    df = pd.concat([df, df.apply(split_course, axis=1)], axis=1, join='inner')
    df = df[df['course_no'] != 'Iblock']
    def collect_class_info(name, cols, created):
        course_df = df[cols]
        if name == 'courses':
            cols[0] = 'id'
        inserts = f"{name}({','.join(cols)},created) values({','.join(['?']*(len(cols)+1))})"
        def make_equal(name):
            return f"{name} = ?"
        cols_same = ' and '.join([make_equal(x) for x in cols])
        def upsert_course_name(row):
            nonlocal cur
            nonlocal name
            nonlocal cols_same
            #If row is an exact match for something already there
            string = f"select created from {name} where {cols_same}"
            if len(db(string,row)) == 0:
                #If the row is going to replace another row, this is will throw an
                #error
                db(f"insert into {inserts}", list(row) + [created])
        #Rows will be in order of cols
        [upsert_course_name(row) for row in course_df.to_numpy()]
    collect_class_info('courses', ['course_no', 'Description', 'Level'], time)
    collect_class_info('sections', ['course_no', 'Term', 'section', 'Room', 'Teacher', 'Schedule'], time)
    con = sqlite3.connect(start + 'calendar.sql')
    cur = con.cursor()
    try:
        df[['created', 'student_name', 'student_hr', 'course_no', 'section', 'Term']].to_sql(
            'enrollments', con=con, if_exists='append', index=False)
        con.close()
    except Exception as e:
        con.close()
        raise e

def pretend_to_be_post(filename):
    import datetime
    information = get_pdf_info(filename)
    insert_sql_data(information, datetime.datetime.utcnow().isoformat(), filename)

class LHS_Calendar:
    global config_dict
    config = config_dict
    tz = pytz.timezone('America/New_York')
    semester_periods = {}
    def get_date(config, num):
        return datetime.datetime(*config['semester_periods'][num],
                tzinfo = pytz.timezone('America/New_York'))
    semester_periods['S 1'] = [get_date(config, 0), get_date(config, 1)]
    semester_periods['S 2'] = [get_date(config, 1), get_date(config, 2)]

    def __init__(self, name, hr):
        while True:
            if not os.path.isdir(start + 'lock'):
                break
        with open(start + 'calendar.ics', 'rb') as f:
            self.cal = pickle.load(f)
        tz = Find_and_replace.tz(self.cal)
        con = sqlite3.connect(start + 'calendar.sql')
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        self.blocks = {"S 1": {}, "S 2": {}}
        self.lunches = {"S 1": [None]*6, "S 2": [None]*6}
        ex = cur.execute("select course_no, description, level, term, room, teacher, schedule from enrollments join courses on enrollments.course_no = courses.id join sections using(course_no, section, term) where student_name = ? and student_hr = ?", [name, hr]).fetchall()
        assert len(ex) > 0
        [self.make_block(row) for row in ex]
        self.cal['X-WR-CALNAME'] = f"{format_name(name)}'s Quickly calendar"
        self.cal['X-WR-CALDESC'] = "Your Quickly calendar. Should sync up to every 12 hours."
        self.dates_to_lunches = {'S 1':{}, 'S 2':{}}
        [[[self.edit_event(func, semester, subcomponent) for subcomponent in
                self.cal.subcomponents]
                for func in [LHS_Calendar.special_edit_event,
                            LHS_Calendar.edit_lunches_of_day,
                            LHS_Calendar.delete_other_lunches,
                            ]]
                for semester in LHS_Calendar.semester_periods]
        self.del_empty_subcomponents()
        self.ical = self.cal.to_ical().decode('utf-8')
        #with open(start + 'test.ics', 'w') as f:
        #    f.write(self.ical)
    
    def make_block(self, row):
        #Counselor seminar course numbers seem to start with CS.
        #CS's don't actually go on for the whole semester, so they are excluded in this version.
        #S stands for semester
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
                    self.blocks[term][letter + number] = rest_of_row
                    self.make_lunch(row, term, letter + number)

    def make_lunch(self, row, term, block):
        day = look(LHS_Calendar.config['lunch_blocks'], block)
        if day is not None:
            course_no = row['course_no']
            room = int(row['Room'])
            if re.match(LHS_Calendar.config['first_lunch'], course_no):
                self.lunches[term][day] = 0
            elif room % 2 == 0: self.lunches[term][day] = 1
            elif room % 2 == 1: self.lunches[term][day] = 2
            else: raise Exception(row, block, "does not fit criteria for any lunches")

    def edit_event(self, func, semester, subcomponent):
        if (type(subcomponent) is ical.cal.Event
            and not subcomponent.is_empty()):
            time = ical.prop.vDDDTypes.from_ical(subcomponent['DTSTART'])
            if type(time) is datetime.date:
                time = Find_and_replace.date_to_datetime(LHS_Calendar.tz, time)
            #If period is None, the period is assumed to be always
            if semester is None or (time >= LHS_Calendar.semester_periods[semester][0]
                and time < LHS_Calendar.semester_periods[semester][1]):
                func(self, semester, subcomponent)

    def special_edit_event(self, semester, event):
        #SUMMARY is the title of the event
        #If SUMMARY is in replacements, SUMMARY is changed to that
        #key's corresponding value (the first parameter), otherwise
        #it is changed to SUMMARY itself (second paramter).
        value = self.blocks[semester].get(event['SUMMARY'])
        if value is not None:
            event['SUMMARY'] = f'{value["Description"]} ({event["SUMMARY"]})'
            event['DESCRIPTION'] = f'{value["Level"]}\n{value["Teacher"]}'
            event['LOCATION'] = value['Room']
        #elif event['SUMMARY'] in LHS_Calendar.config['lunch_blocks']:
        #    event['SUMMARY'] = f'{event["SUMMARY"]} (Lunch)'

    def edit_lunches_of_day(self, semester, event):
        #See if the event is a 'Day #' event.
        day_res = re.match(LHS_Calendar.config['day_pattern'], event['SUMMARY'])
        if day_res:
            #The lunches are stored starting at 0 while Days start at 1
            #This will return a 0, 1, or 2
            lunch_no = self.lunches[semester][int(day_res.group(1)) - 1]
            #If I didn't do copy(), lunches would be removed
            #directly from self.lunches
            other_lunches = LHS_Calendar.config['all_lunches'].copy()
            if lunch_no is not None: other_lunches.pop(lunch_no)
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

def get_fernet():
    with open('lhs_calendar_fernet.txt', 'rb') as f:
        return Fernet(f.read())

def make_ics_query_string(information):
    fernet = get_fernet()
    def make_query(data):
        return urllib.parse.quote_plus(fernet.encrypt(data).decode())
    return f"?0={make_query(str.encode(information['name']))}&1={make_query(int(information['hr']).to_bytes(2, byteorder='big'))}"

def get_user_calendar(enc_name, enc_hr):
    fernet = get_fernet()
    #Flask should have already decoded the strings before this function
    #I'm a little concerned about using urllib to encode the queries but letting
    #Flask decode the queries since they could do it differently
    def decode_query(string):
        return fernet.decrypt(str.encode(string))
    name = decode_query(enc_name).decode()
    hr = int.from_bytes(decode_query(enc_hr), 'big')
    return LHS_Calendar(name, hr).ical

def get_connections(information):
    classes = db('select course_no, section, term from enrollments where student_name = ? and student_hr = ?', [information['name'], information['hr']])
    course_select = "select student_name from enrollments where not (student_name == ? and student_hr = ?) and course_no = ? and section = ? and term = ?" 
    classmates = {class_: db(course_select, (information['name'],information['hr']) + class_)
            for class_ in classes}
    def names(l):
        return [format_name(tuple_of_name[0]) for tuple_of_name in l]
    classmates = {k: names(v) for k, v in classmates.items()}
    def get_coursename(no):
        return db("select description from courses where id = ?", [no])[0][0]
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
    os.makedirs(start + 'lock')
    with open(start + 'calendar.ics', 'wb') as f:
        pickle.dump(ical.Calendar.from_ical(response), f)
    os.rmdir(start + 'lock')

def make_fernet_key():
    with open('lhs_calendar_fernet.txt', 'wb') as f:
        f.write(Fernet.generate_key())

def make_sql_databases():
    con = sqlite3.connect(start + "calendar.sql")
    cursor = con.cursor()
    #It's unclear if the sections are unique to each term or not
    #This isn't autoincrement for a reason I can't remember
    cursor.execute("create table students(name text, hr int, privacy text, primary key (name, hr))")
    cursor.execute("create table courses(id text primary key, created text, Description text, Level text)")
    cursor.execute("create table sections(course_no text, Term text, section int, created text, Room text, Teacher text, Schedule text, primary key (course_no, Term, section), foreign key(course_no) references courses(id))")
    cursor.execute("create table enrollments(id integer primary key, created text, student_name text, student_hr int, course_no text, section int, Term text, foreign key (course_no, section, Term) references sections (course_no, section, Term))")
    #Since I can't see students' IDs I don't need to store anything
    #cursor.execute("create table students(id integer primary key, created text, HR int, name text)")
    con.commit()
    con.close()
