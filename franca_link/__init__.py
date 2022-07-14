import flask
import lhs_connections
import smtplib
import email
import json
import logging
import logging.handlers
import warnings
from pathlib import Path


app = flask.Flask(__name__)
app.config.from_pyfile(f'/etc/{__name__}/config.py')
#For encrypting sessions (cookies) when responding to the client
app.permanent_session_lifetime = app.config['PERMANENT_SESSION_LIFETIME']
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.register_blueprint(lhs_connections.app, url_prefix='/connections')

@app.route('/ignore')
def ignore():
    resp = flask.make_response(flask.redirect('/'))
    resp.set_cookie('ignore', 'True')
    return resp

@app.route('/', methods=['GET'])
def index():
    Path('test.txt').touch()
    return flask.render_template('index.html')
