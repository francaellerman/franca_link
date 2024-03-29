import flask
import logging
import pdfminer
import pickle
import datetime
import os
import pathlib
import pkg_resources
import pathlib
import franca_link.lhs_calendar.worker as worker
import franca_link.my_logging as my_logging
import yaml

wrapper_related = my_logging.wrapper_related('franca_link.calendar')
wrapper = wrapper_related.wrapper

app = flask.Blueprint('calendar', __name__, template_folder='templates', static_folder='static')

start = 'calendar/'

index_ = wrapper()
@app.route('/', methods=['GET'])
@index_
def index():
    #This is causing cookie problems and I'm not willing to fix it
    #def check_for(name):
    #    if not flask.session.get(name):
    #        flask.session.clear()
    #        flask.session[name] = True
    #check_for('post_op_teacher_term_reload')
    #if datetime.date.today() >= datetime.date(2022, 8, 29): check_for('before_first_day')
    global config_
    pre_user_agent = flask.request.headers.get('User-Agent')
    if pre_user_agent:
        user_agent = pre_user_agent.lower()
        if 'iphone' in user_agent:
            mobile = 'iphone'
            platform = 'iphone'
        elif 'android' in user_agent:
            platform = 'android'
            mobile = 'android'
        else:
            mobile = False
            platform = None
        if 'CriOS' in user_agent: browser = 'chrome'
        elif 'safari' in user_agent: browser = 'safari'
        else: browser = None
        return flask.render_template('lhs_calendar/index.html', platform=platform, browser=browser, mobile=mobile, open_=worker.config_dict['open'], config_=worker.config_dict)
    

open_ = wrapper()
@app.route('/open_sesame', methods=['GET'])
@open_
def open():
    global config_
    user_agent = flask.request.headers.get('User-Agent').lower()
    if 'iphone' in user_agent: mobile = 'iphone'
    elif 'android' in user_agent: mobile = 'android'
    else: mobile = False
    return flask.render_template('lhs_calendar/index.html', mobile=mobile, open_=True, config_=worker.config_dict, sesame=True)

about_ = wrapper()
@app.route('/about', methods=['GET'])
@about_
def about():
    resp = flask.render_template('lhs_calendar/about.html')
    return resp

@app.route('/api', methods=['POST'])
def post():
    information = {}
    resp = flask.make_response()
    file = None
    try:
        time = datetime.datetime.utcnow().isoformat()
        file = flask.request.files['pdf']
        if file:
            file.save(os.path.join(start + "pdfs", f'{time}.pdf'))
        information = worker.process_pdf(file, time)
        message = "Request success"
        if file: file = file.filename
    except worker.pdf_verification_exception:
        wrapper_related.exception(extra={'db_created': time, 'pdf_verification_exception': True, 'calendar_name': information.get('name'), 'calendar_hr': information.get('hr'), 'flask_filename': file})
        resp = flask.json.jsonify("pdf_verification_exception")
    except:
        wrapper_related.exception(extra={'db_created': time, 'pdf_verification_exception': False, 'calendar_name': information.get('name'), 'calendar_hr': information.get('hr'), 'flask_filename': file})
        flask.abort(500)
    else:
        wrapper_related.info(message, extra={'db_created': time, 'calendar_name': information.get('name'), 'calendar_hr': information.get('hr'), 'flask_filename': file})
        flask.session.permanent = True
        flask.session['lhs_calendar_name'] = information['name']
        flask.session['lhs_calendar_hr'] = information['hr']
    return resp

get_ics_ = wrapper()
@app.route('/api/ics', methods=['GET'])
@get_ics_
def get_ics():
    for version_ in ['1','2']:
        potential_hr = flask.request.args.get(version_)
        if potential_hr:
            version = version_
            hr = potential_hr
    return flask.Response(worker.get_user_calendar(flask.request.args.get('0'),
        version, hr), mimetype = 'text/calendar')

get_ = wrapper()
@app.route('/api', methods=['GET'])
@get_
def get():
    information = {'name': flask.session.get('lhs_calendar_name'),
            'hr': flask.session.get('lhs_calendar_hr')}
    if not information.get('name') or not information.get('hr'):
        r = 'No ID'
    else:
        r = {'name': worker.display_name(information.get('name'), information.get('hr')),
            'class_list': worker.get_connections(information),
            'ics_link': f'http://franca.link{flask.url_for("calendar.index", _external=False)}api/ics' + worker.make_ics_query_string(information)}
    resp = flask.json.jsonify(r)
    return resp

reset_ = wrapper()
@app.route('/reset', methods=['GET'])
@reset_
def reset():
    flask.session['lhs_calendar_name'] = None
    flask.session['lhs_calendar_hr'] = None
    return flask.make_response()
