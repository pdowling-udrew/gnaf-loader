# script gets all Australian BoM weather station observations
# ... and applies an interpolated temperature to all GNAF points in a 100m grid

# TODO:
#  1. remove temperature biases due to altitude differences
#       a. Add SRTM altitudes to GNAF
#       b. Add interpolated altitude from weather stations to GNAF
#       c. adjust where the difference is > 100m
#  2. generate temps outside the weather station network to catch the ~3,100 GNAF points outside the interpolated area
#

import geopandas
import io
import json
import logging
import matplotlib.pyplot as plt
import multiprocessing
import numpy
import os
import pandas
import psycopg2
import requests
import scipy.interpolate
import sqlalchemy
import struct
import urllib.request
import zipfile

from bs4 import BeautifulSoup
from datetime import datetime
from osgeo import gdal

# where to save the files
output_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "data")

# states to include (note: no "ACT" or "OT" state, Antarctica is part of TAS in BoM observations)
states = [{"name": "NSW", "product": "IDN60801"},
          {"name": "NT", "product": "IDD60801"},
          {"name": "QLD", "product": "IDQ60801"},
          {"name": "SA", "product": "IDS60801"},
          {"name": "TAS", "product": "IDT60801"},
          {"name": "VIC", "product": "IDV60801"},
          {"name": "WA", "product": "IDW60801"},
          {"name": "ANT", "product": "IDT60801"}]

# urls for each state's weather observations
base_url = "http://www.bom.gov.au/{0}/observations/{0}all.shtml"

# postgres connect strings
pg_connect_string = "dbname='geo' host='localhost' port='5432' user='postgres' password='password'"
sql_alchemy_engine_string = "postgresql+psycopg2://postgres:password@localhost/geo"


def main():
    start_time = datetime.now()

    # connect to Postgres
    try:
        pg_conn = psycopg2.connect(pg_connect_string)
        pg_conn.autocommit = True
        pg_cur = pg_conn.cursor()
    except psycopg2.Error:
        logger.fatal("Unable to connect to database\nACTION: Check your Postgres parameters and/or database security")
        return False

    # download weather stations
    station_list = get_weather_stations()
    logger.info("Downloaded {:,} weather stations : {}".format(len(station_list), datetime.now() - start_time))

    obs_list = get_weather_observations(station_list)
    logger.info("Downloaded {:,} latest observations : {}".format(len(obs_list), datetime.now() - start_time))
    start_time = datetime.now()

    # create dataframe of weather stations
    station_df = pandas.DataFrame(station_list)

    # create dataframe of weather obs
    obs_df = pandas.DataFrame(obs_list).drop_duplicates()

    # merge data and add points to dataframe
    df = (obs_df.merge(station_df, on="wmo")
          .drop(["lat", "lon"], axis=1)
          )
    # gdf = geopandas.GeoDataFrame(df, geometry=geopandas.points_from_xy(df.longitude, df.latitude), crs="EPSG:4283")

    # select rows from the last hour with air temps
    rain_trace_df = df[(df["utc_time_diff"] < 3600.0) & (df["rain_trace"].notna()) & (df["rain_trace"] != "-")
                     & (df["longitude"] > 112.0) & (df["longitude"] < 162.0)
                     & (df["latitude"] > -45.0) & (df["latitude"] < -8.0)]

    # extract lat, long and air temp as arrays
    x = rain_trace_df["longitude"].to_numpy()
    y = rain_trace_df["latitude"].to_numpy()
    z = rain_trace_df["rain_trace"].to_numpy()

    # target grid to interpolate to
    xi = numpy.arange(112.0, 162.0, 0.01)
    yi = numpy.arange(-45.0, -8.0, 0.01)
    xi, yi = numpy.meshgrid(xi, yi)

    # interpolate data across the grid
    zi = scipy.interpolate.griddata((x, y), z, (xi, yi), method='cubic')

    # plot
    # fig = plt.figure()
    # ax = fig.add_subplot(111)
    plt.contourf(xi, yi, zi, numpy.arange(-6.1, 45.1, 0.2), extend="both", cmap="Greys")
    # plt.plot(x, y, ".k")
    # plt.xlabel('xi', fontsize=16)
    # plt.ylabel('yi', fontsize=16)
    plt.axis('off')
    plt.savefig(os.path.join(output_path, "interpolated.png"), dpi=300, facecolor="b", edgecolor="red", pad_inches=0.0, metadata=None)
    # plt.close(fig)

    return True


def export_dataframe(pg_cur, df, schema_name, table_name, export_mode):
    # create geodataframe
    gdf = geopandas.GeoDataFrame(df, geometry=geopandas.points_from_xy(df.longitude, df.latitude), crs="EPSG:4283")

    # export to GeoPackage
    # gdf.to_file(os.path.join(output_path, "{}.gpkg".format(table_name)), driver="GPKG")
    #
    # logger.info("Exported points to GeoPackage : {}".format(datetime.now() - start_time))
    # start_time = datetime.now()

    # export to PostGIS
    engine = sqlalchemy.create_engine(sql_alchemy_engine_string)
    gdf.to_postgis(table_name, engine, schema=schema_name, if_exists=export_mode)

    pg_cur.execute("ANALYSE {}.{}".format(schema_name, table_name))
    # pg_cur.execute("ALTER TABLE testing.weather_stations ADD CONSTRAINT weather_stations_pkey PRIMARY KEY (wmo)"
    #                .format(schema_name, table_name))
    pg_cur.execute("ALTER TABLE {0}.{1} CLUSTER ON idx_{1}_geometry".format(schema_name, table_name))
    pg_cur.execute("ALTER TABLE {}.{} RENAME COLUMN geometry TO geom".format(schema_name, table_name))


def get_weather_observations(station_list):
    start_time = datetime.now()

    obs_urls = list()
    obs_list = list()
    for state in states:
        # get URL for web page to scrape
        input_url = base_url.format(state["name"].lower())

        # load and parse web page
        r = requests.get(input_url)
        soup = BeautifulSoup(r.content, features="html.parser")

        # get all links
        links = soup.find_all("a", href=True)

        for link in links:
            url = link["href"]

            if "/products/" in url:
                # only include weather station observations in their home state (border weather obs are duplicated)
                for station in station_list:
                    if station["state"] == state["name"] and station["wmo"] == int(url.split(".")[1]):
                        # change URL to get JSON file of weather obs and add to list
                        obs_url = url.replace("/products/", "http://www.bom.gov.au/fwo/").replace(".shtml", ".json")
                        obs_urls.append(obs_url)

        # with open(os.path.join(output_path, "weather_observations_urls.txt"), "w", newline="") as output_file:
        #     output_file.write("\n".join(obs_urls))

        logger.info("\t - {} : got obs file list : {}".format(state["name"], datetime.now() - start_time))
        start_time = datetime.now()

    # download each obs file using multiprocessing
    pool = multiprocessing.Pool(processes=16)
    results = pool.imap_unordered(run_multiprocessing, obs_urls)

    pool.close()
    pool.join()

    for result in list(results):
        if result.get("error") is not None:
            logger.warning("\t- Failed to parse {}".format(result["error"]))
        else:
            obs_list.append(result)

    return obs_list


def get_weather_stations():
    # get weather stations - obs have poor coordinates
    response = urllib.request.urlopen("ftp://ftp.bom.gov.au/anon2/home/ncc/metadata/sitelists/stations.zip")
    data = io.BytesIO(response.read())
    station_file = zipfile.ZipFile(data, "r", zipfile.ZIP_DEFLATED).read("stations.txt").decode("utf-8")
    stations = station_file.split("\r\n")

    station_list = list()

    # split fixed width file and get the fields we want
    field_widths = (-8, -6, 41, -8, -7, 9, 10, -15, 4, 11, -9, 7)  # negative widths represent ignored fields
    format_string = " ".join("{}{}".format(abs(fw), "x" if fw < 0 else "s") for fw in field_widths)
    field_struct = struct.Struct(format_string)
    parser = field_struct.unpack_from
    # print("fmtstring: {!r}, recsize: {} chars".format(fmtstring, fieldstruct.size))

    # skip first 5 rows (lazy coding!)
    stations.pop(0)
    stations.pop(0)
    stations.pop(0)
    stations.pop(0)
    stations.pop(0)

    # add each station to a list of dictionaries
    for station in stations:
        if len(station) > 128:
            fields = parser(bytes(station, "utf-8"))

            # convert to list
            field_list = list()

            for field in fields:
                field_list.append(field.decode("utf-8").lstrip().rstrip())

            if field_list[5] != "..":
                station_dict = dict()
                station_dict["name"] = field_list[0]
                station_dict["latitude"] = float(field_list[1])
                station_dict["longitude"] = float(field_list[2])
                station_dict["state"] = field_list[3]
                if field_list[4] != "..":
                    station_dict["altitude"] = float(field_list[4])
                station_dict["wmo"] = int(field_list[5])

                station_list.append(station_dict)

    return station_list


def run_multiprocessing(url):
    # file_path = os.path.join(output_path, "obs", url.split("/")[-1])

    # try:
    obs_text = requests.get(url).text

    # with open(file_path, "w", newline="") as output_file:
    #     output_file.write(obs_text)

    obs_json = json.loads(obs_text)
    obs_list = obs_json["observations"]["data"]

    try:
        # default is an error for when there are no observations
        result = dict()
        result["error"] = "{} : No observations".format(url)

        for obs in obs_list:
            if obs["sort_order"] == 0:
                result = obs

                # add utc time
                obs["utc_time"] = datetime.strptime(obs["aifstime_utc"], "%Y%m%d%H%M%S")
                obs["utc_time_diff"] = (datetime.utcnow() - obs["utc_time"]).total_seconds()

    except Exception as ex:
        result = dict()
        result["error"] = "{} : {}".format(url, ex)
        # print(result)

    return result


if __name__ == "__main__":
    full_start_time = datetime.now()

    logger = logging.getLogger()

    # set logger
    log_file = os.path.abspath(__file__).replace(".py", ".log")
    logging.basicConfig(filename=log_file, level=logging.DEBUG, format="%(asctime)s %(message)s",
                        datefmt="%m/%d/%Y %I:%M:%S %p")

    # setup logger to write to screen as well as writing to log file
    # define a Handler which writes INFO messages or higher to the sys.stderr
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    # set a format which is simpler for console use
    formatter = logging.Formatter("%(name)-12s: %(levelname)-8s %(message)s")
    # tell the handler to use this format
    console.setFormatter(formatter)
    # add the handler to the root logger
    logging.getLogger("").addHandler(console)

    logger.info("")
    logger.info("Start weather obs download")
    # psma.check_python_version(logger)

    if main():
        logger.info("Finished successfully! : {}".format(datetime.now() - full_start_time))
    else:
        logger.fatal("Something bad happened!")

    logger.info("")
    logger.info("-------------------------------------------------------------------------------")
