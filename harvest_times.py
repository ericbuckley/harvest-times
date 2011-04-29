import base64
from datetime import datetime
try:
    import json
except:
    from django.utils import simplejson as json
import re
import urllib2
from xml.etree import ElementTree

import bottle
from bottle import Bottle, request

app = Bottle()

TIME_re = re.compile(r'.+{t:(\d+)}.*')

@app.error(403)
def error403(code):
    return 'No auth, No way!'

def auth_required(func):
    def wrapper(*args, **kwargs):
        if not request.auth:
            return app.abort(403)
        return func(*args, **kwargs)
    return wrapper

@app.get('/')
def index():
    return 'Looking for something?'

@app.post('/:domain/:project/:task/')
@auth_required
def harvest_times(domain, project, task):
    username, password = request.auth
    project_id = _find_project_id(domain, project, username, password)
    task_id = _find_task_id(domain, task, username, password)
    data = json.loads(request.body.read())
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
    tree = ElementTree.fromstring(xml)
    for project in tree.getchildren():
        if project.findtext('name') == name:
            return int(project.findtext('id'))
    return None

def _process_commit(commit, username, project_id, task_id):
    if commit['author']['email'] != username:
        # the commit came from someone else, ignore
        return None, None
    message = commit['message']
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
    return xml, hours

def _send_to_harvest(domain, path, username, password, data=None):
    """POST the given data message to the harvest API, if no data is provided GET"""
    url = 'https://%s.harvestapp.com/%s' % (domain, path)
    headers = {'Content-type': 'application/xml', 'Accept': 'application/xml', 
        'Authorization': 'Basic %s' % base64.b64encode('%s:%s' % (username, password))}
    request = urllib2.Request(url, data, headers)
    return urllib2.urlopen(request).read()

def main():
    bottle.run(app, server='gae')

if __name__ == '__main__':
    main()
