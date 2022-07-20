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

start = 'connections/'

#Functions for getting data from any PDF

def get_metadata(fp):
    #This was from some example
    parser = PDFParser(fp)
    doc = PDFDocument(parser)
    parser.set_document(doc)
    doc.set_parser(parser)
    return doc.info[0]

def get_pdf_text(f):
    return PyPDF2.PdfFileReader(f).getPage(0).extractText()

def between(base, str1, str2):
    start = base.find(str1) + len(str1)
    #So that str2 has to be after str1
    return base[start:base.find(str2, start)]

def get_pdf_info(f):
    info = {}
    with pkg_resources.resource_stream('lhs_connections', 'pdf_info_finders.pickle') as file:
        finders = pickle.load(file)
    text = get_pdf_text(f)
    info['name'] = between(text, finders[0], finders[1])
    info['ID'] = between(text, finders[1], finders[2])
    return info

def returning_user_name(id_):
    con = sqlite3.connect(start + 'connections.sql')
    return list(con.cursor().execute(
        "select name from students where id = ?", [int(id_)]))

def insert_sql_data(information, time, file):
    con = sqlite3.connect(start + 'connections.sql')
    cur = con.cursor()
    cur.execute("insert into students(id, created, name) values(?,?,?)", [int(information['ID']), time, information['name']])
    #id_df = pd.DataFrame({'student_id': [information['ID']], 'created': [time],
    #    'student_name': [information['name']]}, index=[])
    #id_df.to_sql('student_names', con=con, if_exists='append', index=False)
    df = tabula.read_pdf(file,
            pages='all')[0][['Course', 'Description', 'Term']]
    df['student_id'] = int(information['ID'])
    df['created'] = time
    def split_course(row):
        middle = row['Course'].find('-')
        course_no = row['Course'][:middle]
        section = int(row['Course'][middle + 1:])
        return pd.Series([course_no, section], index=['course_no', 'section'])
    df = pd.concat([df, df.apply(split_course, axis=1)], axis=1, join='inner')
    df = df.rename(columns={'Description': 'name', 'Term': 'term'})
    df = df[df['course_no'] != 'Iblock']
    course_df = df[['course_no', 'created', 'name']]
    def upsert_course_name(row):
        cur.execute("insert into courses(id, created, name) values(?,?,?) on conflict(id) do nothing", row)
    [upsert_course_name(row) for row in course_df.to_numpy()]
    #course_df = course_df.rename(columns={'course_no': 'id'})
    #course_df = course_df.set_index('id')
    df = df.drop(columns=['Course', 'name'])
    df.to_sql('enrollments', con=con, if_exists='append', index=False)
    #Should throw an error if there are multiple names to the same course ID
    #course_df.to_sql('courses', con=con, if_exists='append')
    con.close()

def format_name(name):
    comma = name.find(',')
    return name[comma + 2:] + ' ' + name[:comma]

def get_connections(id_):
    id_ = int(id_)
    con = sqlite3.connect(start + 'connections.sql')
    cur = con.cursor()
    classes = cur.execute('select course_no, section, term from enrollments where student_id = ?', [id_]).fetchall()
    course_select = "select student_id from enrollments where student_id != ? and course_no = ? and section = ? and term = ?" 
    classmates = {class_: cur.execute(course_select, (id_,) + class_).fetchall()
            for class_ in classes}
    def names(l):
        return [format_name(cur.execute("select name from students where id = ?"
            ,this_id).fetchall()[0][0]) for this_id in l]
    classmates = {k: names(v) for k, v in classmates.items()}
    def get_coursename(no):
        return cur.execute("select name from courses where id = ?", [no]).fetchall()[0][0]
    classmates = [
            {'class':
                {'course': get_coursename(k[0]), 'section': k[1], 'term': k[2]},
            'classmates': v}
            for k, v in classmates.items() if len(v) > 0] #restrict to full classes
    con.close()
    return classmates

#Functions for getting the initial data, only used once

def load_metadata():
    with open(start + "pdf_metadata.pickle", 'wb') as f:
        pickle.dump(get_metadata(open('my_schedule.pdf', 'rb')), f)

def load_info_finder_text():
    with open(start + 'my_schedule.pdf', 'rb') as f:
        text = get_pdf_text(f)
    name = 'Ellerman, Franca'
    student_id = '10001282'
    finders = [text[:text.find(name)],
        between(text, name, student_id),
        '\n']
    with open(start + 'pdf_info_finders.pickle', 'wb') as f:
        pickle.dump(finders, f)

def make_sql_databases():
    con = sqlite3.connect(start + "connections.sql")
    cursor = con.cursor()
    #It's unclear if the sections are unique to each term or not
    cursor.execute("create table enrollments(id integer primary key, created text, student_id int, course_no text, section int, term text)")
    cursor.execute("create table courses(id text primary key, created text, name text)")
    cursor.execute("create table students(id integer primary key, created text, name text)")
    #con.commit()
    con.close()
