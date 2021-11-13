"""
Copyright (c) 2020, Battelle Memorial Institute
All rights reserved.
Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:
1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
The views and conclusions contained in the software and documentation are those
of the authors and should not be interpreted as representing official policies,
either expressed or implied, of the FreeBSD Project.
This material was prepared as an account of work sponsored by an agency of the
United States Government. Neither the United States Government nor the United
States Department of Energy, nor Battelle, nor any of their employees, nor any
jurisdiction or organization that has cooperated in th.e development of these
materials, makes any warranty, express or implied, or assumes any legal
liability or responsibility for the accuracy, completeness, or usefulness or
any information, apparatus, product, software, or process disclosed, or
represents that its use would not infringe privately owned rights.
Reference herein to any specific commercial product, process, or service by
trade name, trademark, manufacturer, or otherwise does not necessarily
constitute or imply its endorsement, recommendation, or favoring by the
United States Government or any agency thereof, or Battelle Memorial Institute.
The views and opinions of authors expressed herein do not necessarily state or
reflect those of the United States Government or any agency thereof.

PACIFIC NORTHWEST NATIONAL LABORATORY
operated by BATTELLE for the UNITED STATES DEPARTMENT OF ENERGY
under Contract DE-AC05-76RL01830
"""

import logging
import importlib
import sys

from volttron.platform.agent import utils
import transactive_utils.models.input_names as data_names

_log = logging.getLogger(__name__)
utils.setup_logging()


class ahuchiller(object):
    def __init__(self, config, parent, **kwargs):
        """
        "model_parameters": {
            "model_type": "ahuchiller.ahuchiller",
            "equipment_configuration": {
                "has_economizer": true,
                "economizer_limit": 65.0,
                "supply_air_setpoint": 55.0,
                "nominal_zone_setpoint": 72.0,
                "building_chiller": true
            },
            "model_configuration": {
                "fan": {
                    "coefficient_group_by": "oad",
                    "coefficients": {
                        20: {"c0": 0.1308, "c1": 0.0004, "c2": -4E-8, "c3": 5E-12},
                        60: {"c0": 0.1308, "c1": 0.0004, "c2": -4E-8, "c3": 5E-12},
                        100: {"c0": 0.1308, "c1": 0.0004, "c2": -4E-8, "c3": 5E-12}
                    }
                },
                "coil": {
                    "COP" : 6.16,
                    "cpAir": 0.0003148
                }
            }
        }
        """
        self.name = 'AhuChiller'
        self.parent = parent
        self.get_input_value = parent.get_input_value
        self.parent.supply_commodity = "ZoneAirFlow"
        self.min_oaf = 0.15
        self.vav_flag = True
        self.has_economizer = True
        self.economizer_limit = 0
        self.mDotAir = 0.
        self.sat_setpoint = 0.
        self.building_chiller = True
        self.tset_avg = 0
        equipment_conf = config.get("equipment_configuration")
        model_conf = config.get("model_configuration")
        # Name mapping between base class and model
        self.sfs_name = data_names.SFS
        self.mat_name = data_names.MAT
        self.dat_name = data_names.DAT
        self.saf_name = data_names.SAF
        self.oat_name = data_names.OAT
        self.rat_name = data_names.RAT
        self.oad_name = data_names.OAD
        # data measurments
        self.sfs = None
        self.mat = None
        self.dat = None
        self.saf = None
        self.oat = None
        self.rat = None
        self.oad = None
        self.fan = Fan(model_conf, self)
        self.coil = CoolingCoil(model_conf, self)

    def equipment_configuration(self, equipment_conf):
        self.min_oaf = equipment_conf.get("minimum_oaf", 0.15)
        self.vav_flag = equipment_conf.get("variable_volume", True)
        self.sat_setpoint = equipment_conf["supply_air_setpoint"]
        self.building_chiller = equipment_conf["building_chiller"]
        self.tset_avg = equipment_conf["nominal_zone_setpoint"]
        self.has_economizer = equipment_conf["has_economizer"]
        if self.has_economizer:
            self.economizer_limit = equipment_conf["economizer_limit"]
        else:
            self.economizer_limit = 0
        self.building_chiller = equipment_conf["building_chiller"]
        self.tset_avg = equipment_conf["nominal_zone_setpoint"]
        self.tDis = self.sat_setpoint

    def update_data(self):
        self.sfs = self.get_input_value(self.sfs_name)
        self.mat = self.get_input_value(self.mat_name)
        self.dat = self.get_input_value(self.dat_name)
        self.saf = self.get_input_value(self.saf_name)
        self.oat = self.get_input_value(self.oat_name)
        self.rat = self.get_input_value(self.rat_name)
        self.oad = self.get_input_value(self.oad_name)

    def input_zone_load(self, q_load):
        if self.vav_flag:
            self.mDotAir = q_load
        else:
            self.tDis = q_load
            self.dat = q_load

    def calculate_load(self, q_load, oat, realtime):
        _log.debug("AHU model - load input: %s -- oat: %s -- realtime market: %s", q_load, oat, realtime)
        self.input_zone_load(q_load)
        return self.calculate_total_power(oat, realtime)

    def calculate_total_power(self, oat, realtime):
        fan_power = self.fan.calculate_power()
        oat = oat if oat is not None else self.oat
        if self.building_chiller:
            coil_load = self.coil.calculate_load(oat, realtime)
        else:
            _log.debug("AHUChiller building does not have chiller!")
            coil_load = 0.0
        return coil_load + max(fan_power, 0)


class Fan:
    def __init__(self, conf, parent):
        if "fan" in conf:
            conf = conf["fan"]
        self.power_unit = conf.get("power_unit", "kW")
        self.coefficient_group_by = conf.get("coefficient_group_by")
        self.coefficient_group_default = conf.get("coefficient_group_default", 20.0)
        coefficients = conf.get("coefficients")
        self.fan_power = 0
        self.c0 = 0
        self.c1 = 0
        self.c2 = 0
        self.c3 = 0
        self.parent = parent
        self.coefficient_dict = {}
        self.init_model(coefficients, conf)

    def init_model(self, coefficients, conf):
        if coefficients is None:
            try:
                c0 = conf["c0"]
                c1 = conf["c1"]
                c2 = conf["c2"]
                c3 = conf["c3"]
            except:
                _log.debug("No fan model coefficients specified")
                sys.exit()
            self.coefficient_dict[100] = {"c0": c0, "c1": c1, "c2": c2, "c3": c3}
            return
        self.coefficient_dict = coefficients

    def update_current_coefficients(self):
        if self.coefficient_group_by is not None:
            measurement = getattr(self.parent, self.coefficient_group_by)
            measurement = measurement if measurement is not None else self.coefficient_group_default
        lst = list(self.coefficient_dict.values())
        if len(lst) == 1:
            _key = lst[0]
        else:
            _key = min(lst, key=lambda x: abs(x-measurement))
        coeff = self.coefficient_dict[_key]
        self.c0 = coeff["c0"]
        self.c1 = coeff["c1"]
        self.c2 = coeff["c2"]
        self.c3 = coeff["c3"]

    def calculate_power(self):
        airflow = self.parent.mDotAir
        fan_power = self.c0 + self.c1 * airflow + self.c2 * airflow**2 + self.c3 * airflow**3  # kW
        return fan_power


class CoolingCoil:
    def __init__(self, conf, parent):
        if "coil" in conf:
            conf = conf["coil"]
        self.cp_air = conf.get("cpAir", 0.0003148)
        self.cop = conf.get("cop", 5.5)
        self.mat = 0.0
        self.dat = 0.0
        self.oat = 0.0
        self.airflow = 0.0
        self.dat_sp = 0.0
        self.has_economizer = parent.has_economizer
        self.economizer_limit = self.parent.economizer_limit
        self.min_oaf = self.parent.min_oaf
        self.avg_vav_sp = self.parent.tset_avg

    def update_data(self):
        self.oat = self.parent.oat
        self.dat = self.parent.dat
        self.mat = self.parent.mat
        self.airflow = self.parent.mDotAir
        self.dat_sp = self.parent.tDis

    def current_coil_load(self):
        try:
            coil_load = self.airflow * self.cp_air * (self.dat - self.mat)
        except:
            _log.debug("AHU for single market requires dat and mat measurements!")
            coil_load = 0.
        # positive value for coil load indicates heating
        return min(0, coil_load)

    def calculate_coil_load(self, oat):
        if oat is None:
            _log.debug("No OAT measurement - Cannot calculate coil load!")
            coil_load = 0
            return coil_load
        if self.has_economizer:
            if oat < self.dat_sp:
                coil_load = 0.0
            elif oat < self.economizer_limit:
                coil_load = self.airflow * self.cp_air * (self.dat_sp - oat)
            else:
                mat = self.avg_vav_sp * (1.0 - self.min_oaf) + self.min_oaf * oat
                coil_load = self.airflow * self.cp_air * (self.dat_sp - mat)
        else:
            mat = self.avg_vav_sp * (1.0 - self.min_oaf) + self.min_oaf * oat
            coil_load = self.airflow * self.cp_air * (self.dat_sp - mat)
        # positive value for coil load indicates heating
        return min(0, coil_load)

    def calculate_load(self, oat, realtime):
        self.update_data()
        if realtime:
            coil_load = self.current_coil_load()
        else:
            coil_load = self.calculate_coil_load(oat)
        return abs(coil_load) / self.cop / 0.9
