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
    if not flask.session.get('post_op_teacher_term_reload'):
        flask.session.clear()
        flask.session['post_op_teacher_term_reload'] = True
    global config_
    browser = flask.request.user_agent.browser
    platform = flask.request.user_agent.platform
    #user_agent = flask.request.headers.get('User-Agent').lower()
    if platform == 'iphone' or platform == 'ipad': mobile = 'iphone'
    elif platform == 'android': mobile = 'android'
    else: mobile = False
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
        file.seek(0)
        worker.verify_pdf(file, time)
        file.seek(0)
        information = worker.get_pdf_info(time)
        #if worker.returning_user_name(information['ID']):
        #    message = "Request success: returning user"
        file.seek(0)
        worker.insert_sql_data(information, time, file)
        message = "Request success"
    except worker.pdf_verification_exception:
        wrapper_related.exception(extra={'db_created': time, 'pdf_verification_exception': True, 'calendar_name': information.get('name'), 'calendar_hr': information.get('hr')})
        resp = flask.json.jsonify("pdf_verification_exception")
    except:
        wrapper_related.exception(extra={'db_created': time, 'pdf_verification_exception': False, 'calendar_name': information.get('name'), 'calendar_hr': information.get('hr')})
        flask.abort(500)
    else:
        wrapper_related.info(message, extra={'db_created': time, 'calendar_name': information.get('name'), 'calendar_hr': information.get('hr')})
        flask.session.permanent = True
        flask.session['lhs_calendar_name'] = information['name']
        flask.session['lhs_calendar_hr'] = information['hr']
    return resp

get_ics_ = wrapper()
@app.route('/api/ics', methods=['GET'])
@get_ics_
def get_ics():
    return flask.Response(worker.get_user_calendar(flask.request.args.get('0'),
        flask.request.args.get('1')), mimetype = 'text/calendar')

get_ = wrapper()
@app.route('/api', methods=['GET'])
@get_
def get():
    information = {'name': flask.session.get('lhs_calendar_name'),
            'hr': flask.session.get('lhs_calendar_hr')}
    if not information.get('name') or not information.get('hr'):
        r = 'No ID'
    else:
        r = {'name': worker.format_name(information.get('name')),
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
