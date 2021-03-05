#!/usr/bin/env bash

# step 1 - make sure POstgres is in your system PATH
# step 2 - make sure postgis raster is enabled on your database: CREATE EXTENSION postgis_raster;

# step 3 - download DEM (~600mb) from:
https://ecat.ga.gov.au/geonetwork/srv/eng/catalog.search#/metadata/69888

# step 4 - import into PostGIS with index
raster2pgsql -c -I -F -s 4326 -t 256x256 \
/Users/s57405/Downloads/3secSRTM_DEM/DEM_ESRI_GRID_16bit_Integer/dem3s_int/hdr.adf testing.srtm_3s_dem \
| psql -U postgres -d geo -h localhost -p 5432

