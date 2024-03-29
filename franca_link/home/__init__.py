import flask
import smtplib
import email
import json
import logging
import logging.handlers
import warnings
from pathlib import Path
import franca_link.my_logging as my_logging
import franca_link.lhs_calendar as lhs_calendar
import naviance_admissions_calculator_web as nacw

my_logging.set_up_logging()
wrapper_related = my_logging.wrapper_related('franca_link')
wrapper = wrapper_related.wrapper

app = flask.Flask(__name__)
app.config.from_pyfile(f'/etc/franca_link/config.py')
#For encrypting sessions (cookies) when responding to the client
app.permanent_session_lifetime = app.config['PERMANENT_SESSION_LIFETIME']
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.register_blueprint(lhs_calendar.app, url_prefix='/quickly')
app.register_blueprint(nacw.app, url_prefix='/calculator')

_ignore = wrapper()
@app.route('/ignore_me', methods=['GET'])
@_ignore
def ignore():
    resp = flask.make_response(flask.redirect('/'))
    resp.set_cookie('ignore', 'True')
    return resp

_slash = wrapper()
@app.route('/', methods=['GET'])
@_slash
def slash():
    return flask.redirect(flask.url_for('calendar.index'))

_index = wrapper()
@app.route('/home/', methods=['GET'])
@_index
def index():
    return flask.render_template('index.html')

_connections_slash = wrapper()
@app.route('/connections/', methods=['GET'])
@_connections_slash
def connections_slash():
    return flask.redirect(flask.url_for('connections'))

_connections = wrapper()
@app.route('/connections', methods=['GET'])
@_connections
def connections():
    return flask.render_template('index.html', connections=True)

@app.route('/gabe', methods=['GET'])
def gabe():
    return flask.render_template('sf_ithaca.html')
