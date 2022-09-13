# Generic/Built-in
import datetime
import errno
import io
import itertools
import os
from typing import Dict, Optional, Tuple
import pandas as pd
import json
import numpy as np
from dataclasses import dataclass
from dataclasses_json import dataclass_json

# Owned
from hisim import component as cp
from hisim import loadtypes as lt
from hisim import log
from hisim import utils
from hisim.simulationparameters import SimulationParameters
from hisim.components.configuration import HouseholdWarmWaterDemandConfig
from hisim.components.configuration import PhysicsConfig

from utspclient import client, datastructures, result_file_filters
from utspclient.helpers import lpg_helper
from utspclient.helpers.lpgpythonbindings import CalcOption, JsonReference
from utspclient.helpers.lpgdata import (
    LoadTypes,
    Households,
    HouseTypes,
    TravelRouteSets,
    TransportationDeviceSets,
    ChargingStationSets,
)


@dataclass_json
@dataclass
class UtspConnectorConfig:
    url: str
    api_key: str
    household: JsonReference
    result_path: str
    travel_route_set: Optional[JsonReference]
    transportation_device_set: Optional[JsonReference]
    charging_station_set: Optional[JsonReference]

    @staticmethod
    def get_default_config(
        url: str = "http://localhost:443/api/v1/profilerequest", api_key: str = ""
    ) -> "UtspConnectorConfig":
        result_path = os.path.join(utils.get_input_directory(), "lpg_profiles")
        config = UtspConnectorConfig(
            url,
            api_key,
            Households.CHR01_Couple_both_at_Work,
            result_path,
            travel_route_set=TravelRouteSets.Travel_Route_Set_for_10km_Commuting_Distance,
            transportation_device_set=TransportationDeviceSets.Bus_and_one_30_km_h_Car,
            charging_station_set=ChargingStationSets.Charging_At_Home_with_03_7_kW,
        )
        return config


class UtspLpgConnector(cp.Component):
    """
    Class component that provides heating generated, the electricity consumed
    by the residents. Data provided or based on LPG exports.
    """

    # Inputs
    WW_MassInput = "Warm Water Mass Input"  # kg/s
    WW_TemperatureInput = "Warm Water Temperature Input"  # °C

    # Outputs
    # output
    WW_MassOutput = "Mass Output"  # kg/s
    WW_TemperatureOutput = "Temperature Output"  # °C
    EnergyDischarged = "Energy Discharged"  # W
    DemandSatisfied = "Demand Satisfied"  # 0 or 1

    NumberByResidents = "NumberByResidents"
    HeatingByResidents = "HeatingByResidents"
    ElectricityOutput = "ElectricityOutput"
    WaterConsumption = "WaterConsumption"

    Electricity_Demand_Forecast_24h = "Electricity_Demand_Forecast_24h"

    # Similar components to connect to:
    # None
    @utils.measure_execution_time
    def __init__(
        self,
        my_simulation_parameters: SimulationParameters,
        config: UtspConnectorConfig,
    ) -> None:
        super().__init__(
            name=UtspLpgConnector.__name__,
            my_simulation_parameters=my_simulation_parameters,
        )
        self.utsp_config = config
        self.build()

        # Inputs - Not Mandatories
        self.ww_mass_input: cp.ComponentInput = self.add_input(
            self.component_name,
            self.WW_MassInput,
            lt.LoadTypes.WARM_WATER,
            lt.Units.KG_PER_SEC,
            False,
        )
        self.ww_temperature_input: cp.ComponentInput = self.add_input(
            self.component_name,
            self.WW_TemperatureInput,
            lt.LoadTypes.WARM_WATER,
            lt.Units.CELSIUS,
            False,
        )

        self.number_of_residentsC: cp.ComponentOutput = self.add_output(
            self.component_name, self.NumberByResidents, lt.LoadTypes.ANY, lt.Units.ANY
        )
        self.heating_by_residentsC: cp.ComponentOutput = self.add_output(
            self.component_name,
            self.HeatingByResidents,
            lt.LoadTypes.HEATING,
            lt.Units.WATT,
        )
        self.electricity_outputC: cp.ComponentOutput = self.add_output(
            object_name=self.component_name,
            field_name=self.ElectricityOutput,
            load_type=lt.LoadTypes.ELECTRICITY,
            unit=lt.Units.WATT,
            postprocessing_flag=lt.InandOutputType.CONSUMPTION,
        )

        self.water_consumptionC: cp.ComponentOutput = self.add_output(
            self.component_name,
            self.WaterConsumption,
            lt.LoadTypes.WARM_WATER,
            lt.Units.LITER,
        )

    def i_save_state(self) -> None:
        pass

    def i_restore_state(self) -> None:
        pass

    def i_prepare_simulation(self) -> None:
        """Prepares the simulation."""
        pass

    def i_doublecheck(self, timestep: int, stsv: cp.SingleTimeStepValues) -> None:
        pass

    def i_simulate(
        self, timestep: int, stsv: cp.SingleTimeStepValues, force_conversion: bool
    ) -> None:
        if self.ww_mass_input.source_output is not None:
            # ww demand
            ww_temperature_demand = HouseholdWarmWaterDemandConfig.ww_temperature_demand

            # From Thermal Energy Storage
            ww_mass_input_per_sec = stsv.get_input_value(self.ww_mass_input)  # kg/s
            # ww_mass_input = ww_mass_input_per_sec * self.seconds_per_timestep           # kg
            ww_mass_input: float = ww_mass_input_per_sec
            ww_temperature_input = stsv.get_input_value(self.ww_temperature_input)  # °C

            # Information import
            freshwater_temperature = (
                HouseholdWarmWaterDemandConfig.freshwater_temperature
            )
            temperature_difference_hot = (
                HouseholdWarmWaterDemandConfig.temperature_difference_hot
            )  # Grädigkeit
            temperature_difference_cold = (
                HouseholdWarmWaterDemandConfig.temperature_difference_cold
            )
            energy_losses_watt = HouseholdWarmWaterDemandConfig.heat_exchanger_losses
            # energy_losses = energy_losses_watt * self.seconds_per_timestep
            energy_losses = 0
            specific_heat = 4180 / 3600

            ww_energy_demand = (
                specific_heat
                * self.water_consumption[timestep]
                * (ww_temperature_demand - freshwater_temperature)
            )

            if (
                ww_temperature_input
                > (ww_temperature_demand + temperature_difference_hot)
                or ww_energy_demand == 0
            ):
                demand_satisfied = 1
            else:
                demand_satisfied = 0

            if ww_energy_demand > 0 and (
                ww_mass_input == 0 and ww_temperature_input == 0
            ):
                """first iteration --> random numbers"""
                ww_temperature_input = 40.45
                ww_mass_input = 9.3

            """
            Warm water is provided by the warmwater stoage.
            The household needs water at a certain temperature. To get the correct temperature the amount of water from
            the wws is regulated and is depending on the temperature provided by the wws. The backflowing water to wws
            is cooled down to the temperature of (freshwater+temperature_difference_cold) --> ww_temperature_output.
            """
            if ww_energy_demand > 0:
                # heating up the freshwater. The mass is consistent
                energy_discharged = ww_energy_demand + energy_losses
                ww_temperature_output: float = (
                    freshwater_temperature + temperature_difference_cold
                )
                ww_mass_input = energy_discharged / (
                    PhysicsConfig.water_specific_heat_capacity
                    * (ww_temperature_input - ww_temperature_output)
                )
            else:
                ww_temperature_output = ww_temperature_input
                ww_mass_input = 0
                energy_discharged = 0

            ww_mass_output = ww_mass_input

            # stsv.set_output_value(self.ww_mass_output, ww_mass_output)
            # stsv.set_output_value(self.ww_temperature_output, ww_temperature_output)
            # stsv.set_output_value(self.demand_satisfied, demand_satisfied)
            # stsv.set_output_value(self.energy_discharged, energy_discharged)

        stsv.set_output_value(
            self.number_of_residentsC, self.number_of_residents[timestep]
        )
        stsv.set_output_value(
            self.heating_by_residentsC, self.heating_by_residents[timestep]
        )
        stsv.set_output_value(
            self.electricity_outputC, self.electricity_consumption[timestep]
        )
        stsv.set_output_value(self.water_consumptionC, self.water_consumption[timestep])

        if self.my_simulation_parameters.system_config.predictive == True:
            last_forecast_timestep = int(
                timestep
                + 24 * 3600 / self.my_simulation_parameters.seconds_per_timestep
            )
            if last_forecast_timestep > len(self.electricity_consumption):
                last_forecast_timestep = len(self.electricity_consumption)
            # log.information( type(self.temperature))
            demandforecast = self.electricity_consumption[
                timestep:last_forecast_timestep
            ]
            self.simulation_repository.set_entry(
                self.Electricity_Demand_Forecast_24h, demandforecast
            )

    def get_resolution(self) -> str:
        """
        Gets the temporal resolution of the simulation as a string in the format
        hh:mm:ss.

        :return: resolution of the simulation
        :rtype: str
        """
        seconds = self.my_simulation_parameters.seconds_per_timestep
        resolution = datetime.timedelta(seconds=seconds)
        return str(resolution)

    def get_profiles_from_utsp(self) -> Tuple[str, str, str, str]:
        """
        Requests the required load profiles from a UTSP server. Returns raw, unparsed result file contents.

        :return: electricity, warm water, high bodily activity and low bodily activity result file contents
        :rtype: Tuple[str]
        """
        # Create an LPG configuration and set the simulation parameters
        start_date = self.my_simulation_parameters.start_date.strftime("%Y-%m-%d")
        # Unlike HiSim the LPG includes the specified end day in the simulation --> subtract one day
        last_day = self.my_simulation_parameters.end_date - datetime.timedelta(days=1)
        end_date = last_day.strftime("%Y-%m-%d")
        simulation_config = lpg_helper.create_basic_lpg_config(
            self.utsp_config.household,
            HouseTypes.HT23_No_Infrastructure_at_all,
            start_date,
            end_date,
            self.get_resolution(),
            travel_route_set=self.utsp_config.travel_route_set,
            transportation_device_set=self.utsp_config.transportation_device_set,
            charging_station_set=self.utsp_config.charging_station_set,
            calc_options=[
                CalcOption.HouseholdSumProfilesCsvNoFlex,
                CalcOption.BodilyActivityStatistics,
                CalcOption.TansportationDeviceJsons,
                CalcOption.FlexibilityEvents,
            ],
        )
        assert simulation_config.CalcSpec is not None

        # Enable simulation of transportation and flexible devices
        simulation_config.CalcSpec.EnableTransportation = True
        simulation_config.CalcSpec.EnableFlexibility = True

        # Define required result files
        electricity = result_file_filters.LPGFilters.sum_hh1(
            LoadTypes.Electricity, no_flex=True
        )
        warm_water = result_file_filters.LPGFilters.sum_hh1(
            LoadTypes.Warm_Water, no_flex=True
        )
        high_activity = result_file_filters.LPGFilters.BodilyActivity.HIGH
        low_activity = result_file_filters.LPGFilters.BodilyActivity.LOW
        flexibility = result_file_filters.LPGFilters.FLEXIBILITY_EVENTS
        required_files = {
            f: datastructures.ResultFileRequirement.REQUIRED
            for f in [
                electricity,
                warm_water,
                high_activity,
                low_activity,
                flexibility,
            ]
        }
        # Define transportation result files
        car_states = result_file_filters.LPGFilters.all_car_states_optional()
        driving_distances = (
            result_file_filters.LPGFilters.all_driving_distances_optional()
        )
        result_files: Dict[str, Optional[datastructures.ResultFileRequirement]] = {
            **required_files,
            **car_states,
            **driving_distances,
        }

        # Prepare the time series request
        request = datastructures.TimeSeriesRequest(
            simulation_config.to_json(), "LPG", required_result_files=result_files  # type: ignore
        )

        log.information("Requesting LPG profiles from the UTSP.")
        # Request the time series
        result = client.request_time_series_and_wait_for_delivery(
            self.utsp_config.url, request, self.utsp_config.api_key
        )

        electricity_file = result.data[electricity].decode()
        warm_water_file = result.data[warm_water].decode()
        high_activity_file = result.data[high_activity].decode()
        low_activity_file = result.data[low_activity].decode()
        flexibility_file = result.data[flexibility].decode()

        # Save flexibility and transportation files
        self.save_result_file(flexibility, flexibility_file)
        for filename in itertools.chain(car_states.keys(), driving_distances.keys()):
            if filename in result.data:
                self.save_result_file(filename, result.data[filename].decode())

        return electricity_file, warm_water_file, high_activity_file, low_activity_file

    def save_result_file(self, name: str, content: str) -> None:
        """
        Saves a result file in the folder specified in the config object

        :param name: the name for the file
        :type name: str
        :param content: the content that will be written into the file
        :type content: str
        """
        filepath = os.path.join(self.utsp_config.result_path, name)
        dir = os.path.dirname(filepath)
        # Create the directory if it does not exist
        try:
            os.makedirs(dir)
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir(dir):
                pass
            else:
                raise
        # Create the result file
        with open(filepath, "w") as f:
            f.write(content)

    def build(self):
        file_exists, cache_filepath = utils.get_cache_file(
            component_key=self.component_name,
            parameter_class=self.utsp_config,
            my_simulation_parameters=self.my_simulation_parameters,
        )
        if file_exists:
            dataframe = pd.read_csv(
                cache_filepath, sep=",", decimal=".", encoding="cp1252"
            )
            self.number_of_residents = dataframe["number_of_residents"].tolist()
            self.heating_by_residents = dataframe["heating_by_residents"].tolist()
            self.electricity_consumption = dataframe["electricity_consumption"].tolist()
            self.water_consumption = dataframe["water_consumption"].tolist()
        else:
            (
                electricity,
                warm_water,
                high_activity,
                low_activity,
            ) = self.get_profiles_from_utsp()

            ################################
            # Calculates heating generated by residents and loads number of residents
            # Heat power generated per resident in W
            # mode 1: awake
            # mode 2: sleeping
            gain_per_person = [150, 100]

            # load occupancy profile
            occupancy_profile = []
            bodily_activity_files = [high_activity, low_activity]
            for filecontent in bodily_activity_files:
                json_filex = json.loads(filecontent)

                occupancy_profile.append(json_filex)

            # see how long csv files from LPG are to check if averaging has to be done and calculate desired length
            steps_original = len(occupancy_profile[0]["Values"])
            simulation_time_span = (
                self.my_simulation_parameters.end_date
                - self.my_simulation_parameters.start_date
            )
            steps_desired = int(
                simulation_time_span.days
                * 24
                * (3600 / self.my_simulation_parameters.seconds_per_timestep)
            )
            steps_ratio = int(steps_original / steps_desired)

            # initialize number of residence and heating by residents
            self.heating_by_residents = [0] * steps_desired
            self.number_of_residents = [0] * steps_desired

            # load electricity consumption and water consumption
            electricity_data = io.StringIO(electricity)
            pre_electricity_consumption = pd.read_csv(
                electricity_data,
                sep=";",
                decimal=".",
                encoding="cp1252",
            )
            water_data = io.StringIO(warm_water)
            pre_water_consumption = pd.read_csv(
                water_data,
                sep=";",
                decimal=".",
                encoding="cp1252",
            )

            # convert electricity consumption and water consumption to desired format and unit
            self.electricity_consumption = pd.to_numeric(
                pre_electricity_consumption["Sum [kWh]"] * 1000 * 60
            ).tolist()  # 1 kWh/min == 60W / min
            self.water_consumption = pd.to_numeric(
                pre_water_consumption["Sum [L]"]
            ).tolist()

            # process data when time resolution of inputs matches timeresolution of simulation
            if steps_original == steps_desired:
                for mode in range(len(gain_per_person)):
                    for timestep in range(steps_original):
                        self.number_of_residents[timestep] += occupancy_profile[mode][
                            "Values"
                        ][timestep]
                        self.heating_by_residents[timestep] = (
                            self.heating_by_residents[timestep]
                            + gain_per_person[mode]
                            * occupancy_profile[mode]["Values"][timestep]
                        )

            # average data, when time resolution of inputs is coarser than time resolution of simulation
            elif steps_original > steps_desired:
                for mode in range(len(gain_per_person)):
                    for timestep in range(steps_desired):
                        number_of_residents_av = (
                            sum(
                                occupancy_profile[mode]["Values"][
                                    timestep
                                    * steps_ratio : (timestep + 1)
                                    * steps_ratio
                                ]
                            )
                            / steps_ratio
                        )
                        self.number_of_residents[timestep] += np.round(
                            number_of_residents_av
                        )
                        self.heating_by_residents[timestep] = (
                            self.heating_by_residents[timestep]
                            + gain_per_person[mode] * number_of_residents_av
                        )
                # power needs averaging, not sum
                self.electricity_consumption = [
                    sum(self.electricity_consumption[n : n + steps_ratio]) / steps_ratio
                    for n in range(0, steps_original, steps_ratio)
                ]
                self.water_consumption = [
                    sum(self.water_consumption[n : n + steps_ratio])
                    for n in range(0, steps_original, steps_ratio)
                ]

            else:
                raise Exception(
                    "input from LPG is given in wrong time resolution - or at least cannot be interpolated correctly"
                )

            # Saves data in cache
            data = np.transpose(
                [
                    self.number_of_residents,
                    self.heating_by_residents,
                    self.electricity_consumption,
                    self.water_consumption,
                ]
            )
            database = pd.DataFrame(
                data,
                columns=[
                    "number_of_residents",
                    "heating_by_residents",
                    "electricity_consumption",
                    "water_consumption",
                ],
            )

            database.to_csv(cache_filepath)
            del data
            del database
            # utils.save_cache("Occupancy", parameters, database)
        self.max_hot_water_demand = max(self.water_consumption)

    def write_to_report(self):
        lines = []
        lines.append("Name: {}".format(self.component_name))
        # lines.append("Profile: {}".format(self.profile_name))
        return lines
