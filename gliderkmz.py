#!/usr/bin/env python

"""
Author: lgarzio on 2/28/2024
Last modified: lgarzio on 2/28/2024
Test glider kmz generation
"""

import os
import datetime as dt
import pandas as pd
import numpy as np
import requests
from jinja2 import Environment, FileSystemLoader, meta


def format_ts_str(timestamp):
    return dt.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')


glider = 'ru40'
savedir = '/Users/garzio/Documents/repo/lgarzio/gliderkmz/templates/'

# load the template
environment = Environment(loader=FileSystemLoader(savedir))
template = environment.get_template('template_ts.kml')
track_template = environment.get_template('track_macro.kml')

glider_api = 'https://marine.rutgers.edu/cool/data/gliders/api/'
active_deployments = requests.get(f'{glider_api}deployments/?active').json()['data']
for ad in active_deployments:
    glider_name = ad['glider_name']
    if glider_name == glider:
        filename = f'{glider_name}-test.kml'
        savefile = os.path.join(savedir, filename)
        deployment = ad['deployment_name']

        # last surfacing
        last_surfacing = ad['last_surfacing']
        ls_connect_ts = format_ts_str(last_surfacing['connect_ts'])
        ls_disconnect_ts = format_ts_str(last_surfacing['disconnect_ts'])
        ls_gps_connect_ts = dt.datetime.fromtimestamp(last_surfacing['connect_time_epoch'], dt.UTC).strftime('%Y-%m-%d %H:%M')

        # track
        track_dict = dict(
            gps_epoch=np.array([], dtype='int'),
            lon=np.array([], dtype='float'),
            lat=np.array([], dtype='float')
        )
        track_features = requests.get(f'{glider_api}tracks/?deployment={deployment}').json()['features']
        for tf in track_features:
            if tf['geometry']['type'] == 'Point':
                track_dict['gps_epoch'] = np.append(track_dict['gps_epoch'], tf['properties']['gps_epoch'])
                track_dict['lon'] = np.append(track_dict['lon'], tf['geometry']['coordinates'][0])
                track_dict['lat'] = np.append(track_dict['lat'], tf['geometry']['coordinates'][1])
        track_df = pd.DataFrame(track_dict)
        track_df.sort_values(by='gps_epoch', inplace=True, ignore_index=True)

        track_dict = dict()
        for idx, row in track_df.iterrows():
            if idx > 0:
                prev_row = track_df.iloc[idx-1]
                start = dt.datetime.fromtimestamp(prev_row.gps_epoch, dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
                end = dt.datetime.fromtimestamp(row.gps_epoch, dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
                track_dict[idx] = dict(
                    start=start,
                    end=end,
                    start_lon=prev_row.lon,
                    start_lat=prev_row.lat,
                    end_lon=row.lon,
                    end_lat=row.lat
                )

        content = template.render(
            glider_name=glider_name,
            ls_connect_ts=ls_connect_ts,
            ls_disconnect_ts=ls_disconnect_ts,
            ls_nmea_lat=last_surfacing['gps_lat'],
            ls_nmea_lon=last_surfacing['gps_lon'],
            ls_gps_connect_ts=ls_gps_connect_ts,
            ls_reason=last_surfacing['surface_reason'],
            ls_mission=last_surfacing['mission'],
            ls_filename=last_surfacing['filename'],
            ls_8x3_filename=last_surfacing['the8x3_filename'],
            ls_dsvr_log=last_surfacing['dsvr_log_name'],
            track_info=track_dict
        )

        with open(savefile, mode="w", encoding="utf-8") as message:
            message.write(content)
        print('done')


# template_source = environment.loader.get_source(environment, 'ru40.kml')
# parsed_content = environment.parse(template_source)
