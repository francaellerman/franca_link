import flask
import logging
import pdfminer
import pickle
import datetime
import os
import pathlib
import warnings
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
        with warnings.catch_warnings(record=True) as caught_warnings:
            file = flask.request.files['pdf']
            md = worker.get_metadata(file)
            with pkg_resources.resource_stream('franca_link.lhs_connections', 'pdf_metadata.pickle') as f:
                franca_md = pickle.load(f)
            if not md['ModDate'] == md['CreationDate']:
                raise Exception("Metadata does not fit the criteria: same mod and creation", md['ModDate'], md['CreationDate'])
            if not md['Creator'] == franca_md['Creator']:
                raise Exception("Metadata does not fit the criteria: same creator", md['Creator'], franca_md['Creator'])
            if not md['Producer'] == franca_md['Producer']:
                raise Exception("Metadata does not fit the criteria: same producer", md['Producer'], franca_md['Producer'])
            if len(caught_warnings) > 0:
                raise Exception("Getting PDF metadata raised a warning")
        information = worker.get_pdf_info(file)
        if worker.returning_user_name(information['ID']):
            message = "Request success: returning user"
        else:
            file.seek(0)
            worker.insert_sql_data(information, time, file)
            file.seek(0)
            file.save(os.path.join(start + "pdfs", f'{time}.pdf'))
            message = "Request success"
        file.close()
    except:
        wrapper_related.exception(id_=information.get('ID'))
        #Could download file if something goes wrong
        flask.abort(500)
    else:
        wrapper_related.info(message, id_=information['ID'])
        flask.session['ID'] = information['ID']
    return resp

get_ = wrapper()
@app.route('/api', methods=['GET'])
@get_
def get():
    id_ = flask.session.get('ID')
    if not id_:
        r = 'No ID'
    else:
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
