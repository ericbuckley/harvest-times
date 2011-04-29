#!/usr/bin/env python

import bottle
from harvest_times import app

bottle.debug(True)
bottle.run(app, port=8000, reloader=True)
