import base64
from datetime import datetime
from django.utils import simplejson as json
import re
import urllib2

import bottle
from bottle import request, get, post, error, abort

TIME_re = re.compile(r'.+{t:(\d+)}.*')

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
    data = json.loads(request.body.read())
    count = 0
    time = 0
    for commit in data['commits']:
        data, hours = _process_commit(commit, project, task)
        if data:
            count += 1
            time += hours
            try:
                _send_to_harvest(domain, 'daily/add', username, password, data)
            except:
                return {'error': True, 'message': 'Harvest API is down'}
    return {'success': True, 'commits_added': count, 'hours': hours}

def _process_commit(commit, project, task):
    date_no_timezone = commit['timestamp'][:-6]
    date = datetime.strptime(date_no_timezone, '%a, %d %b %Y %H:%M:%S')
    date = date.strftime('%Y-%m-%d')
    message = commit['message']
    match = TIME_re.match(message)
    if not match:
        return None, None
    minutes = int(match.group(1))
    hours = minutes / 60.0
    data = {'notes': message, 'hours': hours, 'project': project,
            'task': task, 'spent_at': date}
    xml = ''.join(['<%s>%s</%s>' % (k,v,k) for k,v in data.items()])
    return '<request>%s</request>' % xml, hours

def _send_to_harvest(domain, path, username, password, data=None):
    """POST the given data message to the harvest API, if no data is provided GET"""
    url = 'https://%s.harvestapp.com/%s' % (domain, path)
    headers = {'Content-type': 'application/xml', 'Accept': 'application/xml', 
        'Authorization': 'Basic %s' % base64.b64encode('%s:%s' % (username, password))}
    request = urllib2.Request(url, data, headers)
    return urllib2.urlopen(request).read()

def main():
    bottle.run(server='gae')

if __name__ == '__main__':
    main()
