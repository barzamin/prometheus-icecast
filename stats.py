#!/usr/bin/env python3

from lxml import etree
from pprint import pprint
import requests
from flask import Flask, Response
from collections import defaultdict
import time

app = Flask(__name__)

ICECAST_BASE='http://localhost:8000'
ICECAST_CFG = '/etc/icecast/icecast.xml'
MOUNTPOINTS = ['/blissomradio']

STATS = {
    'icecast_source_listeners': {'ty': 'gauge'},
    'icecast_source_peak_listeners': {'ty': 'counter'},
    'icecast_source_total_bytes_read': {'ty': 'counter'},
    'icecast_source_total_bytes_sent': {'ty': 'counter'},
}

def get_icecast_creds():
    with open(ICECAST_CFG) as f:
        cfg = etree.parse(f)
    icecast = cfg.getroot()
    user = icecast.find('authentication/admin-user').text
    password = icecast.find('authentication/admin-password').text

    return (user, password)

def stats_from_source(el):
    return {
        'icecast_source_listeners': int(el.find('./listeners').text),
        'icecast_source_peak_listeners': int(el.find('./listener_peak').text),
        'icecast_source_total_bytes_read': int(el.find('./total_bytes_read').text),
        'icecast_source_total_bytes_sent': int(el.find('./total_bytes_sent').text),
    }

def emit_metric_header(name, type_='gauge', help_=None) -> str:
    out = ''
    if help_ is not None:
        out += f'# HELP {name} {help_}\n'
    out += f'# TYPE {name} {type_}\n'

    return out

def emit_metric(name, val, ts, params=None):
    out = f'{name}'
    if params:
        out += '{' + ','.join([f'{k}="{v}"' for k, v in params.items()]) + '}'
    out += f' {val} {ts}'

    return out

def millis_ts():
    return time.time_ns()//1000000

def collect():
    ts = millis_ts()
    creds = get_icecast_creds()
    r = requests.get(f'{ICECAST_BASE}/admin/stats', auth=creds)
    
    icestats = etree.fromstring(r.content)
    stats = defaultdict(list)
    for mountpoint in MOUNTPOINTS:
        el = icestats.find(f'./source[@mount=\'{mountpoint}\']')
        if el is not None:
            for statname, val in stats_from_source(el).items():
                stats[statname].append(({'mountpoint': mountpoint}, val))
    
    out = ''
    for statname, statdetails in STATS.items():
        out += emit_metric_header(statname, statdetails['ty'])
        for (params, val) in stats[statname]:
            out += emit_metric(statname, val, ts, params)

        out += '\n'
    
    return out

@app.route('/metrics')
def metrics():
    resp = Response(collect(), status=200, mimetype='text/plain')
    resp.headers['Content-Type'] = 'text/plain; version=0.0.4'
    return resp

if __name__ == '__main__':
    app.run(port=5555)
    # print(collect())
