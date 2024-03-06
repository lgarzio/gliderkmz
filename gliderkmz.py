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
from jinja2 import Environment, FileSystemLoader
pd.set_option('display.width', 320, "display.max_columns", 10)


# def format_ts_str(timestamp):
#     return dt.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')

def add_sensor_values(data_dict, sensor_name, sensor_api_data):
    """
    Add values from specific sensors to dictionary summaries
    """
    sensor_df = pd.DataFrame(sensor_api_data)
    disconnect_ts_format = dt.datetime.strptime(data_dict['disconnect_ts'], '%Y-%m-%d %H:%M').strftime('%Y-%m-%dT%H:%M:00')
    try:
        sensor_value = sensor_df.loc[sensor_df.ts == disconnect_ts_format].value.values[0]
    except IndexError:
        sensor_value = None
    data_dict[sensor_name] = sensor_value


def build_deployment_lastsurf_dict(data):
    """
    Build the dictionaries for the data that populates the deployment and last surfacing locations in the kml
    :param data: dictionary
    """
    connect_ts = format_ts_epoch(data['connect_time_epoch'])
    disconnect_ts = format_ts_epoch(data['disconnect_time_epoch'])
    gps_connect_ts = format_ts_epoch(data['gps_timestamp_epoch'])
    try:
        waypoint_range_km = data['waypoint_range_meters'] / 1000
    except TypeError:
        waypoint_range_km = None

    return_dict = dict(
        connect_ts=connect_ts,
        disconnect_ts=disconnect_ts,
        nmea_lat=data['gps_lat'],
        nmea_lon=data['gps_lon'],
        gps_connect_ts=gps_connect_ts,
        reason=data['surface_reason'],
        mission=data['mission'],
        filename=data['filename'],
        filename_8x3=data['the8x3_filename'],
        dsvr_log=data['dsvr_log_name'],
        segment_ewo=f"{data['segment_errors']}/{data['segment_warnings']}/{data['segment_oddities']}",
        mission_ewo=f"{data['mission_errors']}/{data['mission_warnings']}/{data['mission_oddities']}",
        total_ewo=f"{data['total_errors']}/{data['total_warnings']}/{data['total_oddities']}",
        dive_time=None,  # minutes  # ***** need to find all of these in the API *****
        dive_dist=None,  # km
        total_speed=None,  # m/s
        total_speed_bearing=None,
        current_speed=None,  # m/s
        current_speed_bearing=None,
        glide_speed=None,  # m/s
        glide_speed_bearing=None,
        waypoint_lat=data['waypoint_lat'],
        waypoint_lon=data['waypoint_lon'],
        waypoint_range=waypoint_range_km,
        waypoint_bearing=data['waypoint_bearing_degrees']
    )

    return return_dict


def format_ts_epoch(timestamp):
    return dt.datetime.fromtimestamp(timestamp, dt.UTC).strftime('%Y-%m-%d %H:%M')


glider = 'ru40'
sensor_list = ['m_battery', 'm_vacuum']
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

        # build the dictionary for the last surfacing information
        last_surfacing_dict = build_deployment_lastsurf_dict(ad['last_surfacing'])

        # add values for battery and vacuum to the last surfacing information
        for sensor in sensor_list:
            sensor_api = requests.get(f'{glider_api}sensors/?deployment={deployment}&sensor={sensor}').json()['data']
            add_sensor_values(last_surfacing_dict, sensor, sensor_api)

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

        surface_df = pd.DataFrame(surface_events)

        # find the deployment location surface record  ***** this doesn't match up with the current kmzs *****
        for se in surface_events:
            if se['surfacing_id'] == deployment_sid:

                # build the dictionary for the deployment information
                deployment_dict = build_deployment_lastsurf_dict(se)

                # add values for battery and vacuum to deployment information
                for sensor in sensor_list:
                    sensor_api = requests.get(f'{glider_api}sensors/?deployment={deployment}&sensor={sensor}').json()['data']
                    add_sensor_values(deployment_dict, sensor, sensor_api)

        # render all of the information into the kml template
        content = template.render(
            ts_now=ts_now,
            glider_name=glider_name,
            glider_tail=glider_tail,
            ls_connect_ts=last_surfacing_dict['connect_ts'],
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
