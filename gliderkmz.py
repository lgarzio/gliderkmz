#!/usr/bin/env python

"""
Author: lgarzio on 2/28/2024
Last modified: lgarzio on 3/5/2024
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


def format_ts_epoch(timestamp):
    return dt.datetime.fromtimestamp(timestamp, dt.UTC).strftime('%Y-%m-%d %H:%M')


glider = 'ru40'
savedir = '/Users/garzio/Documents/repo/lgarzio/gliderkmz/templates/'
glider_tails = 'http://marine.rutgers.edu/~kerfoot/icons/glider_tails/'
ts_now = dt.datetime.now(dt.UTC).strftime('%m/%d/%y %H:%M')

# load the template
environment = Environment(loader=FileSystemLoader(savedir))
template = environment.get_template('template_ts.kml')
track_template = environment.get_template('track_macro.kml')
surfacing_template = environment.get_template('surface_event_macro.kml')
text_box_template = environment.get_template('text_box_macro.kml')

glider_api = 'https://marine.rutgers.edu/cool/data/gliders/api/'
active_deployments = requests.get(f'{glider_api}deployments/?active').json()['data']
for ad in active_deployments:
    glider_name = ad['glider_name']
    if glider_name == glider:
        filename = f'{glider_name}-test2.kml'
        savefile = os.path.join(savedir, filename)
        deployment = ad['deployment_name']
        glider_tail = os.path.join(glider_tails, f'{glider_name}.png')

        # last surfacing
        ls = ad['last_surfacing']

        ls_connect_ts = format_ts_str(ls['connect_ts'])
        ls_disconnect_ts = format_ts_str(ls['disconnect_ts'])
        ls_gps_connect_ts = format_ts_epoch(ls['connect_time_epoch'])

        last_surfacing_dict = dict(
            connect_ts=ls_connect_ts,
            disconnect_ts=ls_disconnect_ts,
            nmea_lat=ls['gps_lat'],
            nmea_lon=ls['gps_lon'],
            gps_connect_ts=ls_gps_connect_ts,
            reason=ls['surface_reason'],
            mission=ls['mission'],
            filename=ls['filename'],
            filename_8x3=ls['the8x3_filename'],
            dsvr_log=ls['dsvr_log_name'],
        )

        # track information
        # gather track timestamp and location from the API
        track_dict = dict(
            gps_epoch=np.array([], dtype='int'),
            lon=np.array([], dtype='float'),
            lat=np.array([], dtype='float'),
            sid=np.array([], dtype='int')
        )
        track_features = requests.get(f'{glider_api}tracks/?deployment={deployment}').json()['features']
        for tf in track_features:
            if tf['geometry']['type'] == 'Point':
                track_dict['gps_epoch'] = np.append(track_dict['gps_epoch'], tf['properties']['gps_epoch'])
                track_dict['lon'] = np.append(track_dict['lon'], tf['geometry']['coordinates'][0])
                track_dict['lat'] = np.append(track_dict['lat'], tf['geometry']['coordinates'][1])
                track_dict['sid'] = np.append(track_dict['sid'], tf['properties']['sid'])
        track_df = pd.DataFrame(track_dict)
        track_df.sort_values(by='gps_epoch', inplace=True, ignore_index=True)

        # find the deployment id
        deployment_sid = int(track_df.iloc[0]['sid'])

        # build the dictionary that contains the track information to input into the kml template
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

        # surface events
        surface_events = requests.get(f'{glider_api}surfacings/?deployment={deployment}').json()['data']

        # find the deployment location surface record
        for se in surface_events:
            if se['surfacing_id'] == deployment_sid:
                deploy_connect_ts = format_ts_epoch(se['connect_time_epoch'])
                deploy_disconnect_ts = format_ts_epoch(se['disconnect_time_epoch'])
                deploy_gps_connect_ts = format_ts_epoch(se['gps_timestamp_epoch'])

                deployment_dict = dict(
                    connect_ts=deploy_connect_ts,
                    disconnect_ts=deploy_disconnect_ts,
                    nmea_lat=se['gps_lat'],
                    nmea_lon=se['gps_lon'],
                    gps_connect_ts=deploy_gps_connect_ts,
                    reason=se['surface_reason'],
                    mission=se['mission'],
                    filename=se['filename'],
                    filename_8x3=se['the8x3_filename'],
                    dsvr_log=se['dsvr_log_name'],
                )

        # render all of the information into the kml template
        content = template.render(
            ts_now=ts_now,
            glider_name=glider_name,
            glider_tail=glider_tail,
            last_surfacing_info=last_surfacing_dict,
            deployment_info=deployment_dict,
            track_info=track_dict,
            surface_event_info=surface_events
        )

        with open(savefile, mode="w", encoding="utf-8") as message:
            message.write(content)
        print('done')


# template_source = environment.loader.get_source(environment, 'ru40.kml')
# parsed_content = environment.parse(template_source)
