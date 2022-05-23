from typing import Optional, List, Union
import hisim.components.random_numbers
from hisim.simulator import SimulationParameters
from hisim.components import loadprofilegenerator_connector
from hisim.components import advanced_battery_bslib
from hisim.components import weather
from hisim.components import generic_gas_heater
from hisim.components import controller_l2_energy_management_system as cl2
from hisim.components import generic_pv_system
from hisim.components import building
from hisim.components import advanced_fuel_cell
from hisim.components.random_numbers import RandomNumbers
from hisim.components.example_transformer import Transformer
from hisim import loadtypes as lt
from hisim import component as cp
import numpy as np
import os
from hisim import utils
def basic_household_explicit(my_sim, my_simulation_parameters: Optional[SimulationParameters] = None):
    year = 2018
    seconds_per_timestep = 60 * 15
    # Set weather
    location = "Aachen"
    # Set occupancy
    occupancy_profile = "CH01"
    # Set photovoltaic system
    time = 2019
    power = 3E3
    load_module_data = False
    module_name = "Hanwha_HSL60P6_PA_4_250T__2013_"
    integrateInverter = True
    inverter_name = "ABB__MICRO_0_25_I_OUTD_US_208_208V__CEC_2014_"
    if my_simulation_parameters is None:
        my_simulation_parameters = SimulationParameters.full_year_all_options(year=year,
                                                                                 seconds_per_timestep=seconds_per_timestep)
    my_sim.SimulationParameters = my_simulation_parameters

    my_advanced_battery_1 = advanced_battery_bslib.Battery(my_simulation_parameters=my_simulation_parameters,
                                                             system_id='SG1',
                                                             p_inv_custom=5.0,
                                                             e_bat_custom=10.0,
                                                             name="Battery1")
    my_advanced_battery_2 = advanced_battery_bslib.Battery(my_simulation_parameters=my_simulation_parameters,
                                                             system_id='SG1',
                                                             p_inv_custom=2.5,
                                                             e_bat_custom=5.0,
                                                             name="Battery2")
    my_advanced_fuel_cell_1 = advanced_fuel_cell.CHP(my_simulation_parameters=my_simulation_parameters,
                                                             gas_type="Methan",
                                                             name="CHP1",
                                                             operating_mode="electricity")
    my_advanced_fuel_cell_2 = advanced_fuel_cell.CHP(my_simulation_parameters=my_simulation_parameters,
                                                             gas_type="Methan",
                                                             name="CHP2",
                                                             operating_mode="electricity")
    my_cl2 = cl2.ControllerGeneric(my_simulation_parameters=my_simulation_parameters)

    my_occupancy = loadprofilegenerator_connector.Occupancy( profile_name=occupancy_profile, my_simulation_parameters = my_simulation_parameters )

    my_weather = weather.Weather( location=location, my_simulation_parameters = my_simulation_parameters,
                                  my_simulation_repository = my_sim.simulation_repository )

    my_photovoltaic_system = generic_pv_system.PVSystem(my_simulation_parameters=my_simulation_parameters,
                                                        my_simulation_repository=my_sim.simulation_repository,
                                                        time=time,
                                                        location=location,
                                                        power=power,
                                                        load_module_data=load_module_data,
                                                        module_name=module_name,
                                                        integrateInverter=integrateInverter,
                                                        inverter_name=inverter_name)
    my_photovoltaic_system.connect_only_predefined_connections(my_weather)

    my_cl2.connect_input(my_cl2.ElectricityConsumptionBuilding,
                                         my_occupancy.ComponentName,
                                         my_occupancy.ElectricityOutput)
    my_cl2.connect_input(my_cl2.ElectricityOutputPvs,
                                         my_photovoltaic_system.ComponentName,
                                         my_photovoltaic_system.ElectricityOutput)
    my_cl2.add_component_input_and_connect( source_component_class=my_advanced_battery_1,
                                               source_component_output=my_advanced_battery_1.AcBatteryPower,
                                               source_load_type= lt.LoadTypes.Electricity,
                                               source_unit= lt.Units.Watt,
                                               source_tags=[lt.ComponentType.Battery,lt.InandOutputType.ElectricityReal],
                                               source_weight=1)
    my_cl2.add_component_input_and_connect( source_component_class=my_advanced_battery_2,
                                               source_component_output=my_advanced_battery_2.AcBatteryPower,
                                               source_load_type= lt.LoadTypes.Electricity,
                                               source_unit= lt.Units.Watt,
                                               source_tags=[lt.ComponentType.Battery,lt.InandOutputType.ElectricityReal],
                                               source_weight=2)

    electricity_to_or_from_battery_target_1 = my_cl2.add_component_output(source_output_name=lt.InandOutputType.ElectricityTarget,
                                               source_tags=[lt.ComponentType.Battery],
                                               source_weight=1,
                                               source_load_type= lt.LoadTypes.Electricity,
                                               source_unit= lt.Units.Watt)
    electricity_to_or_from_battery_target_2 = my_cl2.add_component_output(source_output_name=lt.InandOutputType.ElectricityTarget,
                                               source_tags=[lt.ComponentType.Battery],
                                               source_weight=2,
                                               source_load_type= lt.LoadTypes.Electricity,
                                               source_unit= lt.Units.Watt)

    my_advanced_battery_1.connect_dynamic_input(input_fieldname=advanced_battery_bslib.Battery.LoadingPowerInput,
                                        src_object=electricity_to_or_from_battery_target_1)
    my_advanced_battery_2.connect_dynamic_input(input_fieldname=advanced_battery_bslib.Battery.LoadingPowerInput,
                                        src_object=electricity_to_or_from_battery_target_2)

    my_cl2.add_component_input_and_connect( source_component_class=my_advanced_fuel_cell_1,
                                               source_component_output=my_advanced_fuel_cell_1.ElectricityOutput,
                                               source_load_type= lt.LoadTypes.Electricity,
                                               source_unit= lt.Units.Watt,
                                               source_tags=[lt.ComponentType.FuelCell,lt.InandOutputType.ElectricityReal],
                                               source_weight=3)
    my_cl2.add_component_input_and_connect( source_component_class=my_advanced_fuel_cell_2,
                                               source_component_output=my_advanced_fuel_cell_2.ElectricityOutput,
                                               source_load_type= lt.LoadTypes.Electricity,
                                               source_unit= lt.Units.Watt,
                                               source_tags=[lt.ComponentType.FuelCell,lt.InandOutputType.ElectricityReal],
                                               source_weight=4)

    electricity_from_fuel_cell_target_1 = my_cl2.add_component_output(source_output_name=lt.InandOutputType.ElectricityTarget,
                                               source_tags=[lt.ComponentType.FuelCell],
                                               source_weight=3,
                                               source_load_type= lt.LoadTypes.Electricity,
                                               source_unit= lt.Units.Watt)
    electricity_from_fuel_cell_target_2 = my_cl2.add_component_output(source_output_name=lt.InandOutputType.ElectricityTarget,
                                               source_tags=[lt.ComponentType.FuelCell],
                                               source_weight=4,
                                               source_load_type= lt.LoadTypes.Electricity,
                                               source_unit= lt.Units.Watt)

    my_advanced_fuel_cell_1.connect_dynamic_input(input_fieldname=advanced_fuel_cell.CHP.ElectricityFromCHPTarget,
                                        src_object=electricity_from_fuel_cell_target_1)
    my_advanced_fuel_cell_2.connect_dynamic_input(input_fieldname=advanced_fuel_cell.CHP.ElectricityFromCHPTarget,
                                        src_object=electricity_from_fuel_cell_target_2)

    my_sim.add_component(my_advanced_battery_1)
    my_sim.add_component(my_advanced_battery_2)
    my_sim.add_component(my_advanced_fuel_cell_1)
    my_sim.add_component(my_advanced_fuel_cell_2)
    my_sim.add_component(my_cl2)
    my_sim.add_component( my_weather )
    my_sim.add_component( my_occupancy )
    my_sim.add_component(my_photovoltaic_system)
