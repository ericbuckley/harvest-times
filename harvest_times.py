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

import bottle
from bottle import request, get, post, error, abort

TIME_re = re.compile(r'.+{t:(\d+)}.*')

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
    project_id = _find_project_id(domain, project, username, password)
    task_id = _find_task_id(domain, task, username, password)
    try:
        data = json.loads(request.POST['payload'])
    except Exception, e:
        logging.fatal('Payload Exception: %s' % e)
    count = 0
    time = 0
    for commit in data['commits']:
        data, hours = _process_commit(commit, username, project_id, task_id)
        if data:
            count += 1
            time += hours
            try:
                _send_to_harvest(domain, 'daily/add', username, password, data)
            except:
                return {'error': True, 'message': 'Harvest API is down'}
    return {'success': True, 'commits_added': count, 'hours': hours}

def _find_project_id(domain, project, username, password):
    response = _send_to_harvest(domain, 'projects', username, password)
    return _find_id_by_name(response, project)

def _find_task_id(domain, task, username, password):
    response = _send_to_harvest(domain, 'tasks', username, password)
    return _find_id_by_name(response, task)

def _find_id_by_name(xml, name):
    tree = ElementTree.fromstring(xml.content)
    for project in tree.getchildren():
        if project.findtext('name') == name:
            return int(project.findtext('id'))
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
    date = date.strftime('%Y-%m-%d')
    xml = """
        <request>
            <notes>%s</notes>
            <hours>%s</hours>
            <project_id type="integer">%s</project_id>
            <task_id type="integer">%s</task_id>
            <spent_at type="date">%s</spent_at>
        </request>
    """ % (message, hours, project_id, task_id, date)
    logging.debug('xml: %s' % xml)
    return str(xml.replace('\n', ' ')), hours

def _send_to_harvest(domain, path, username, password, data=None):
    """POST the given data message to the harvest API, if no data is provided GET"""
    url = 'https://%s.harvestapp.com/%s' % (domain, path)
    headers = {'Content-type': 'application/xml', 'Accept': 'application/xml', 
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
