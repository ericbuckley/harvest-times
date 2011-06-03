import base64
from datetime import datetime
try:
    import json
except:
    from django.utils import simplejson as json
import logging
import re
from xml.etree import ElementTree

from google.appengine.api import urlfetch

from pytz.gae import pytz

import bottle
from bottle import request, get, post, error, abort

TIME_re = re.compile(r'.+{t:(\d+)}.*')
UTC=pytz.utc
EST=pytz.timezone('US/Eastern')

def dbg():
    """ Enter pdb in App Engine

    Renable system streams for it.
    """
    import pdb
    import sys
    pdb.Pdb(stdin=getattr(sys,'__stdin__'),stdout=getattr(sys,'__stderr__')).set_trace(sys._getframe().f_back)

@error(403)
def error403(code):
    return 'No auth, No way!'

def auth_required(func):
    def wrapper(*args, **kwargs):
        if not request.auth:
            return abort(403)
        return func(*args, **kwargs)
    return wrapper

@get('/')
def index():
    return 'Looking for something?'

@post('/:domain/:project/:task/')
@auth_required
def harvest_times(domain, project, task):
    username, password = request.auth
    logging.debug('auth username: %s / auth password: %s' % (username, password))
    project_id = _find_project_id(domain, project, username, password)
    logging.debug('project id: %s' % project_id)
    task_id = _find_task_id(domain, task, username, password)
    logging.debug('task id: %s' % task_id)
    try:
        data = json.loads(request.POST['payload'])
    except Exception, e:
        logging.fatal('Payload Exception: %s' % e)
    count = 0
    time = 0
    for commit in data['commits']:
        data, hours = _process_commit(commit, username, project_id, task_id)
        if data:
            logging.debug('push %s to harvest' % data)
            count += 1
            time += hours
            try:
                _send_to_harvest(domain, 'daily/add', username, password, data)
            except:
                return {'error': True, 'message': 'Harvest API is down'}
    return {'success': True, 'commits_added': count, 'hours': hours}

def _find_project_id(domain, project_name, username, password):
    response = _send_to_harvest(domain, 'projects', username, password)
    for project in json.loads(response.content):
        data = project['project']
        if data['name'] == project_name or data['code'] == project_name:
            return data['id']
    return None

def _find_task_id(domain, task_name, username, password):
    response = _send_to_harvest(domain, 'tasks', username, password)
    for task in json.loads(response.content):
        data = task['task']
        if data['name'] == task_name:
            return data['id']
    return None

def _process_commit(commit, username, project_id, task_id):
    logging.debug('username: %s' % username)
    logging.debug('author: %s' % commit['author']['email'])
    if commit['author']['email'] != username:
        # the commit came from someone else, ignore
        return None, None
    message = commit['message']
    logging.debug('message: %s' % message)
    match = TIME_re.match(message)
    if not match:
        # the commit doesn't contain time tracking, ignore
        return None, None
    minutes = int(match.group(1))
    hours = minutes / 60.0
    date_no_timezone = commit['timestamp'][:-6]
    date = datetime.strptime(date_no_timezone, '%a, %d %b %Y %H:%M:%S')
    date = UTC.localize(date).astimezone(EST)
    date = date.strftime('%Y-%m-%d')
    data = {
        'notes': message,
        'hours': hours,
        'project_id': project_id,
        'task_id': task_id,
        'spent_at': date
        }
    return json.dumps(data), hours

def _send_to_harvest(domain, path, username, password, data=None):
    """POST the given data message to the harvest API, if no data is provided GET"""
    url = 'https://%s.harvestapp.com/%s' % (domain, path)
    headers = {'Content-type': 'application/json', 'Accept': 'application/json', 
        'Authorization': 'Basic %s' % base64.b64encode('%s:%s' % (username, password))}
    logging.debug(url)
    logging.debug(data)
    logging.debug(headers)
    if data:
        return urlfetch.fetch(url=url, payload=data, method=urlfetch.POST, headers=headers)
    else:
        return urlfetch.fetch(url=url, headers=headers)

def main():
    bottle.run(server='gae')

if __name__ == '__main__':
    main()
