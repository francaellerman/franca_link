import flask
import logging
import pdfminer
import pickle
import datetime
import os
import pathlib
import pkg_resources
import pathlib
import franca_link.lhs_connections.worker as worker
import franca_link.my_logging as my_logging
import yaml

wrapper_related = my_logging.wrapper_related('franca_link.connections')
wrapper = wrapper_related.wrapper

app = flask.Blueprint('connections', __name__, template_folder='templates', static_folder='static')

start = 'connections/'

with open('/etc/franca_link/lhs_connections_config.yaml', 'rb') as f:
    config_ = yaml.safe_load(f)

index_ = wrapper()
@app.route('/', methods=['GET'])
@index_
def index():
    global config_
    user_agent = flask.request.headers.get('User-Agent').lower()
    if 'iphone' in user_agent or 'android' in user_agent: mobile = True
    else: mobile = False
    return flask.render_template('lhs_connections/index.html', mobile=mobile,
        links=config_['links'])

about_ = wrapper()
@app.route('/about', methods=['GET'])
@about_
def about():
    resp = flask.render_template('lhs_connections/about.html')
    return resp

@app.route('/api', methods=['POST'])
def post():
    information = {}
    resp = flask.make_response()
    file = None
    try:
        time = datetime.datetime.utcnow().isoformat()
        file = flask.request.files['pdf']
        worker.verify_pdf(file)
        information = worker.get_pdf_info(file)
        if worker.returning_user_name(information['ID']):
            message = "Request success: returning user"
        else:
            file.seek(0)
            worker.insert_sql_data(information, time, file)
            message = "Request success"
    except worker.pdf_verification_exception:
        wrapper_related.exception(id_=information.get('ID'), extra={'db_created': time, 'pdf_verification_exception': True})
        resp = flask.json.jsonify("pdf_verification_exception")
    except Exception:
        wrapper_related.exception(id_=information.get('ID'), extra={'db_created': time})
        flask.abort(500)
    else:
        wrapper_related.info(message, id_=information['ID'], extra={'db_created': time})
        flask.session['ID'] = information['ID']
    finally:
        if file:
            file.seek(0)
            file.save(os.path.join(start + "pdfs", f'{time}.pdf'))
            file.close()
    return resp

get_ = wrapper()
@app.route('/api', methods=['GET'])
@get_
def get():
    id_ = flask.session.get('ID')
    if not id_:
        r = 'No ID'
    else:
        #If this is out of range then the POST claimed to work by sending an ID
        #cookie but didn't actually since the name isn't in the students table
        name = worker.format_name(worker.returning_user_name(id_)[0][0])
        r = {'name': name,
            'class_list': worker.get_connections(id_)}
    resp = flask.json.jsonify(r)
    return resp

reset_ = wrapper()
@app.route('/reset', methods=['GET'])
@reset_
def reset():
    flask.session['ID'] = None
    return flask.make_response()
