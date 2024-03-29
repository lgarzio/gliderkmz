#!/usr/bin/env python

"""
Author: lgarzio on 2/28/2024
Last modified: lgarzio on 3/12/2024
Test glider kmz generation
"""

import os
import datetime as dt
import pandas as pd
import numpy as np
import requests
import simplekml
import yaml
from jinja2 import Environment, FileSystemLoader
pd.set_option('display.width', 320, "display.max_columns", 10)


# def format_ts_str(timestamp):
#     return dt.datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M')

def add_sensor_values(data_dict, sensor_name, sdf):
    """
    Find data from a sensor within a specific time range (+/- 5 minutes from surface disconnect time). Add the median
    of the values to the dictionary summaries
    """
    yml_file = '/Users/garzio/Documents/repo/lgarzio/gliderkmz/configs/sensor_thresholds.yml'
    with open(yml_file) as f:
        sensor_thresholds = yaml.safe_load(f)
    thresholds = sensor_thresholds[sensor_name]

    ts = pd.to_datetime(data_dict['disconnect_ts'])
    t0 = ts - pd.Timedelta(minutes=5)
    t1 = ts + pd.Timedelta(minutes=5)

    try:
        sensor_value = np.round(np.median(sdf.loc[np.logical_and(sdf.ts >= t0, sdf.ts <= t1)].value), 2)
        if sensor_value <= thresholds['fail_threshold']:
            bgcolor = 'darkred'
        elif thresholds['suspect_span'][0] < sensor_value < thresholds['suspect_span'][1]:
            bgcolor = 'BEA60E'  # yellow BEA60E
        else:
            bgcolor = 'green'
    except IndexError:
        sensor_value = None
        bgcolor = 'BEA60E'  # yellow BEA60E
    data_dict[sensor_name] = sensor_value
    data_dict[f'{sensor_name}_bgcolor'] = bgcolor


def build_popup_dict(data):
    """
    Build the dictionaries for the data that populates the pop-up text boxes
    :param data: dictionary
    """
    connect_ts = format_ts_epoch(data['connect_time_epoch'])
    disconnect_ts = format_ts_epoch(data['disconnect_time_epoch'])
    gps_connect_ts = format_ts_epoch(data['gps_timestamp_epoch'])

    gps_connect_timedelta = dt.datetime.fromtimestamp(data['connect_time_epoch'], dt.UTC) - dt.datetime.fromtimestamp(data['gps_timestamp_epoch'], dt.UTC)
    if gps_connect_timedelta.seconds >= 3600:  # 3600 = 1 hour
        gps_bgcolor = 'darkred'
    elif 3600 > gps_connect_timedelta.seconds > 600:  # between 10 mins (600) and 1 hour (3600)
        gps_bgcolor = 'BEA60E'  # yellow BEA60E
    else:  # < 10 minutes
        gps_bgcolor = 'green'

    try:
        waypoint_range_km = data['waypoint_range_meters'] / 1000
    except TypeError:
        waypoint_range_km = None

    popup_dict = dict(
        connect_ts=connect_ts,
        disconnect_ts=disconnect_ts,
        gps_lat=np.round(convert_nmea_degrees(data['gps_lat']), 2),
        gps_lon=np.round(convert_nmea_degrees(data['gps_lon']), 2),
        gps_connect_ts=gps_connect_ts,
        gps_bgcolor=gps_bgcolor,
        reason=data['surface_reason'],
        mission=data['mission'],
        filename=data['filename'],
        filename_8x3=data['the8x3_filename'],
        dsvr_log=data['dsvr_log_name'],
        segment_ewo=f"{data['segment_errors']}/{data['segment_warnings']}/{data['segment_oddities']}",
        mission_ewo=f"{data['mission_errors']}/{data['mission_warnings']}/{data['mission_oddities']}",
        total_ewo=f"{data['total_errors']}/{data['total_warnings']}/{data['total_oddities']}",
        waypoint_lat=data['waypoint_lat'],
        waypoint_lon=data['waypoint_lon'],
        waypoint_range=waypoint_range_km,
        waypoint_bearing=data['waypoint_bearing_degrees']
    )

    return popup_dict


def convert_nmea_degrees(x):
    """
    Convert lat/lon coordinates from nmea to decimal degrees
    """
    try:
        degrees = np.sign(x) * (np.floor(np.abs(x)/100) + np.mod(np.abs(x), 100) / 60)
    except TypeError:
        degrees = None

    return degrees


def format_ts_epoch(timestamp):
    return dt.datetime.fromtimestamp(timestamp, dt.UTC).strftime('%Y-%m-%d %H:%M')


#gliders = ['maracoos_02', 'ru40']
sensor_list = ['m_battery', 'm_vacuum']
templatedir = '/Users/garzio/Documents/repo/lgarzio/gliderkmz/templates/'
savedir = '/Users/garzio/Documents/repo/lgarzio/gliderkmz/templates/'
savefile = os.path.join(savedir, 'active_deployments-ts-test.kml')
kml_type = 'deployed_ts_uv'  # 'deployed' 'deployed_ts' 'deployed_uv' 'deployed_ts_uv'
glider_tails = 'https://rucool.marine.rutgers.edu/gliders/glider_tails/'  # /www/web/rucool/gliders/glider_tails
# old glider tails location: https://marine.rutgers.edu/~kerfoot/icons/glider_tails/

# inspired by colorblind-friendly colormap (https://mpetroff.net/2018/03/color-cycle-picker/) for tracks/points
# NOTE: kml colors are encoded backwards from the HTML convention. HTML colors are "#rrggbbaa": Red Green Blue Alpha,
# while KML colors are "AABBGGRR": Alpha Blue Green Red.

# teal ('ffe9d043'), pink ('ff9e36d7'), purple ('ffd7369e'), yellow ('ff43d0e9'), orange ('ff3877f3'),
# green ('ff83c995'), gray ('ffc4c9d8')
colors = ['ffe9d043', 'ff9e36d7', 'ffd7369e', 'ff43d0e9', 'ff3877f3', 'ff83c995', 'ffc4c9d8']

ts_now = dt.datetime.now(dt.UTC).strftime('%m/%d/%y %H:%M')

# load the templates
environment = Environment(loader=FileSystemLoader(templatedir))
template = environment.get_template('active_deployments_template.kml')
format_template = environment.get_template('format_active_deployments_macro.kml')
deployment_template = environment.get_template('deployment_macro.kml')
track_template = environment.get_template('track_macro.kml')
surfacing_template = environment.get_template('surface_event_macro.kml')
text_box_template = environment.get_template('text_box_macro.kml')

glider_api = 'https://marine.rutgers.edu/cool/data/gliders/api/'
active_deployments = requests.get(f'{glider_api}deployments/?active').json()['data']

if len(active_deployments) > len(colors):
    repeatx = int(np.ceil(len(active_deployments) / len(colors)))
    colors = colors * repeatx

# build the formatting for the kml file
format_dict = dict()
for idx, ad in enumerate(active_deployments):
    glider_name = ad['glider_name']
    print(f'{glider_name}: color {colors[idx]}')
    #if glider_name in gliders:
    deployment = ad['deployment_name']
    format_dict[deployment] = dict(
        name=glider_name,
        glider_tail=os.path.join(glider_tails, f'{glider_name}.png'),
        deployment_color=colors[idx]
    )

# build all of the information to populate each deployment
deployment_dict = dict()
for ad in active_deployments:
    glider_name = ad['glider_name']
    #if glider_name in gliders:
    deployment = ad['deployment_name']
    glider_tail = os.path.join(glider_tails, f'{glider_name}.png')

    # get distance flow and calculate days deployed
    distance_flown_km = ad['distance_flown_km']
    try:
        end = dt.datetime.fromtimestamp(ad['end_date_epoch'], dt.UTC)
    except TypeError:
        end = dt.datetime.now(dt.UTC)
    start = dt.datetime.fromtimestamp(ad['start_date_epoch'], dt.UTC)
    seconds_deployed = ((end - start).days * 86400) + (end - start).seconds
    days_deployed = np.round(seconds_deployed / 86400, 2)

    # grab the data from the surface sensors and store in a dictionary (so you only have to hit the API once
    # per sensor per deployment)
    sensor_data = dict()
    for sensor in sensor_list:
        sensor_api = requests.get(f'{glider_api}sensors/?deployment={deployment}&sensor={sensor}').json()['data']
        sensor_df = pd.DataFrame(sensor_api)
        sensor_df.sort_values(by='epoch_seconds', inplace=True, ignore_index=True)
        sensor_df['ts'] = pd.to_datetime(sensor_df['ts'])
        sensor_data[sensor] = sensor_df

    # build the dictionary for the last surfacing information
    ls_api = ad['last_surfacing']
    last_surfacing_popup_dict = build_popup_dict(ls_api)
    ls_gps_lat_degrees = ls_api['gps_lat_degrees']
    ls_gps_lon_degrees = ls_api['gps_lon_degrees']

    # add values for battery and vacuum to the last surfacing information
    for sensor in sensor_list:
        add_sensor_values(last_surfacing_popup_dict, sensor, sensor_data[sensor])

    # add dive information (time, distance, speed)
    last_surfacing_popup_dict['dive_time'] = int(np.round(ls_api['dive_time_seconds'] / 60)),  # minutes
    last_surfacing_popup_dict['dive_dist'] = np.round(ls_api['segment_distance_m'] / 1000, 2),  # km
    last_surfacing_popup_dict['total_speed'] = None  # m/s
    last_surfacing_popup_dict['total_speed_bearing'] = None
    last_surfacing_popup_dict['current_speed'] = None  # m/s
    last_surfacing_popup_dict['current_speed_bearing'] = None
    last_surfacing_popup_dict['glide_speed'] = None  # m/s
    last_surfacing_popup_dict['glide_speed_bearing'] = None

    # current waypoint information
    cwpt_lat = ls_api['waypoint_lat']
    cwpt_lon = ls_api['waypoint_lon']
    cwpt_lat_degress = convert_nmea_degrees(cwpt_lat)
    cwpt_lon_degress = convert_nmea_degrees(cwpt_lon)

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

    # add the last surfacing to the dictionary
    track_dict['gps_epoch'] = np.append(track_dict['gps_epoch'], ls_api['connect_time_epoch'])
    track_dict['lon'] = np.append(track_dict['lon'], ls_api['gps_lon_degrees'])
    track_dict['lat'] = np.append(track_dict['lat'], ls_api['gps_lat_degrees'])
    track_dict['sid'] = np.append(track_dict['sid'], ls_api['surfacing_id'])

    # convert to dataframe to sort by time
    track_df = pd.DataFrame(track_dict)
    track_df.sort_values(by='gps_epoch', inplace=True, ignore_index=True)

    # find the deployment id
    deployment_sid = int(track_df.iloc[0]['sid'])

    if kml_type in ['deployed', 'deployed_uv']:
        track_df = track_df.copy()[['lon', 'lat']]
        track_df['height'] = 4.999999999999999
        track_values = track_df.values.tolist()
        kml = simplekml.Kml()
        track_data = kml.newlinestring(name="track")
        for values in track_values:
            track_data.coords.addcoordinates([(values[0], values[1], values[2])])
    elif kml_type in ['deployed_ts', 'deployed_ts_uv']:
        # build the dictionary that contains the track information to input into the kml template
        track_data = dict()
        for idx, row in track_df.iterrows():
            if idx > 0:
                prev_row = track_df.iloc[idx - 1]
                start = dt.datetime.fromtimestamp(prev_row.gps_epoch, dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
                end = dt.datetime.fromtimestamp(row.gps_epoch, dt.UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
                track_data[idx] = dict(
                    start=start,
                    end=end,
                    start_lon=prev_row.lon,
                    start_lat=prev_row.lat,
                    end_lon=row.lon,
                    end_lat=row.lat
                )

    # surface events
    surface_events = requests.get(f'{glider_api}surfacings/?deployment={deployment}').json()['data']
    surf_df = pd.DataFrame(surface_events)

    # calculate previous 24 hours
    t24h = pd.to_datetime(ts_now) - pd.Timedelta(hours=24)

    surface_events_dict = dict()
    currents_dict = dict()
    call_length_seconds = 0

    # build the information for the surfacings and depth-averaged currents
    for idx, se in enumerate(surface_events):
        call_length_seconds = call_length_seconds + se['call_length_seconds']
        surface_event_popup = build_popup_dict(se)

        # define surfacing grouping (e.g. last 24 hours or day)
        se_ts = pd.to_datetime(surface_event_popup['connect_ts'])

        if se_ts >= t24h:
            folder_name = 'Last 24 Hours'
            style_name = 'RecentSurfacing'
        else:
            folder_name = se_ts.strftime('%Y-%m-%d')
            style_name = 'Surfacing'

        # define folder name for depth-average currents
        currents_folder_name = se_ts.strftime('%Y-%m-%d')
        connect_datetime = dt.datetime.fromtimestamp(se['connect_time_epoch'], dt.UTC)

        # add the folder name to the surface events dictionary if it's not already there
        try:
            surface_events_dict[folder_name]
        except KeyError:
            surface_events_dict[folder_name] = dict()

        # add the folder name to the currents dictionary if it's not already there
        try:
            currents_dict[currents_folder_name]
        except KeyError:
            currents_dict[currents_folder_name] = dict()

        # calculate depth-average currents  **************TO DO**************
        lon_deg_end = se['gps_lon_degrees'] - .05
        lat_deg_end = se['gps_lat_degrees'] - .05

        currents_dict[currents_folder_name][idx] = dict(
            connect_HHMM=connect_datetime.strftime('%H:%M'),
            connect_ts_Z=connect_datetime.strftime('%Y-%m-%dT%H:%M:%SZ'),
            lon_degrees_start=se['gps_lon_degrees'],
            lat_degrees_start=se['gps_lat_degrees'],
            lon_degrees_end=lon_deg_end,
            lat_degrees_end=lat_deg_end,
        )

        surface_events_dict[folder_name][idx] = dict(
            connect_ts=surface_event_popup['connect_ts'],
            connect_ts_Z=connect_datetime.strftime('%Y-%m-%dT%H:%M:%SZ'),
            gps_lat_degrees=se['gps_lat_degrees'],
            gps_lon_degrees=se['gps_lon_degrees'],
            style_name=style_name,
            surface_event_popup=surface_event_popup
        )

        # add data from sensors to the popup
        for sensor in sensor_list:
            add_sensor_values(surface_events_dict[folder_name][idx]['surface_event_popup'], sensor, sensor_data[sensor])

        # add dive information to the surfacing event (time, distance, speed)
        surface_events_dict[folder_name][idx]['surface_event_popup']['dive_time'] = None,  # minutes
        surface_events_dict[folder_name][idx]['surface_event_popup']['dive_dist'] = None,  # km
        surface_events_dict[folder_name][idx]['surface_event_popup']['total_speed'] = None  # m/s
        surface_events_dict[folder_name][idx]['surface_event_popup']['total_speed_bearing'] = None
        surface_events_dict[folder_name][idx]['surface_event_popup']['current_speed'] = None  # m/s
        surface_events_dict[folder_name][idx]['surface_event_popup']['current_speed_bearing'] = None
        surface_events_dict[folder_name][idx]['surface_event_popup']['glide_speed'] = None  # m/s
        surface_events_dict[folder_name][idx]['surface_event_popup']['glide_speed_bearing'] = None

        # find the deployment location surface record  ***** this doesn't match up with the current kmzs *****
        if se['surfacing_id'] == deployment_sid:

            # build the dictionary for the deployment information
            deployment_popup_dict = build_popup_dict(se)
            deployment_ts_Z = dt.datetime.fromtimestamp(se['connect_time_epoch'], dt.UTC).strftime(
                '%Y-%m-%dT%H:%M:%SZ')
            deployment_gps_lat_degrees = se['gps_lat_degrees']
            deployment_gps_lon_degrees = se['gps_lon_degrees']

            # add values for battery and vacuum to deployment information
            for sensor in sensor_list:
                add_sensor_values(deployment_popup_dict, sensor, sensor_data[sensor])

            # add dive information (time, distance, speed)
            deployment_popup_dict['dive_time'] = 'N/A',  # minutes
            deployment_popup_dict['dive_dist'] = 'N/A',  # km
            deployment_popup_dict['total_speed'] = 'N/A'  # m/s
            deployment_popup_dict['total_speed_bearing'] = 'N/A'
            deployment_popup_dict['current_speed'] = None  # m/s
            deployment_popup_dict['current_speed_bearing'] = None
            deployment_popup_dict['glide_speed'] = 'N/A'  # m/s
            deployment_popup_dict['glide_speed_bearing'] = 'N/A'

    deployment_dict[deployment] = dict(
        ts_now=ts_now,
        glider_name=glider_name,
        glider_tail=glider_tail,
        ls_connect_ts=last_surfacing_popup_dict['connect_ts'],
        deploy_ts_Z=deployment_ts_Z,
        ls_gps_lat_degrees=ls_gps_lat_degrees,
        ls_gps_lon_degrees=ls_gps_lon_degrees,
        last_surfacing_popup=last_surfacing_popup_dict,
        deploy_connect_ts=deployment_popup_dict['connect_ts'],
        deploy_gps_lat_degrees=deployment_gps_lat_degrees,
        deploy_gps_lon_degrees=deployment_gps_lon_degrees,
        deployment_popup=deployment_popup_dict,
        cwpt_since=last_surfacing_popup_dict['disconnect_ts'],
        cwpt_lat=cwpt_lat,
        cwpt_lon=cwpt_lon,
        cwpt_lat_degrees=cwpt_lat_degress,
        cwpt_lon_degrees=cwpt_lon_degress,
        distance_flown_km=distance_flown_km,
        days_deployed=days_deployed,
        iridium_mins=int(np.round(call_length_seconds / 60)),
        track_info=track_data,
        surface_event_info=surface_events_dict,
        currents_info=currents_dict
    )

# render all of the information into the kml template
content = template.render(
    kml_type=kml_type,
    format_info=format_dict,
    deployment_info=deployment_dict
)

with open(savefile, mode="w", encoding="utf-8") as message:
    message.write(content)
