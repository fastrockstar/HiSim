﻿# Typical Meteorological Year (TMY) data derived from the NSRDB time-series datasets.

**Acknowledgement**:
Data are extracted from NREL National Solar Radiation Database https://nsrdb.nrel.gov/data-viewer/download/intro

License
Creative Commons Attribution 3.0 United States License

**Description**:

Released to the public as part of the Department of Energy's Open Energy Data Initiative, the National Solar Radiation Database (NSRDB) is a serially complete collection of hourly and half-hourly values of the three most common measurements of solar radiation – global horizontal, direct normal, and diffuse horizontal irradiance — and meteorological data. These data have been collected at a sufficient number of locations and temporal and spatial scales to accurately represent regional solar radiation climates.

In order to use the data in simulations with a temporal resolution of 1min or 15min, the data set was extended by linear interpolation. While this approach is justifiable for air pressure and temperature, for example, it does not depict high fluctuations in solar radiation. Therefore, based on the one-minute open data measurement data set of the Baseline Surface Radiation Network, with an algorithm by Hofmann et. al. the time series of global radiation are newly generated for all test reference years. Another algorithm by Hofmann et. al. was used to calculate the corresponding diffuse radiation times series.

Final datasets are the .dat file located in the folder of the desired region. Example: final dataset for Madrid is loacted in the folder Madrid in the file Madrid.dat. Remark: csv files are not processed and cannot be used. 

**Test reference stations / regions**

No. | lon | lat |region
--- | --- | --- | --- 
1 | 37.37 | -5.98 |Seville
2 | 40.45| -3.7 | Madrid


```
* **columns per file**:
```
datetime [yyyy-MM-dd hh:mm:ss+01:00/02:00]
Temperature [degC]
pressure [hPa]
wind direction [deg]
wind speed [m/s]
surface albedo [-]
direct irradiance [W/m^2]
diffuse irradiance [W/m^2]
Direct horizontal irradiance [W/m^2]
Direct normal irradiance [W/m^2]
global horizontal irradiance [W/m^2]
```
* **length**: 1 year
* **time increment**: 60s / 900s / 3600s

**Important hints**:
- *A value with, for example, a timestamp 12:00:00 represents the mean value from this timestamp until the following timestamp.*
- *datetime column is in CET / CEST*