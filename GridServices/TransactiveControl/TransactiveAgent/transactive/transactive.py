"""
Copyright (c) 2022, Battelle Memorial Institute
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

import os
import sys
import logging
import datetime
import gevent
from dateutil import parser
from datetime import timedelta
import uuid
import gevent

from volttron.platform.vip.agent import Agent, Core, PubSub, RPC, compat
from volttron.platform.agent import utils
from volttron.platform.agent.utils import (get_aware_utc_now, format_timestamp, parse_timestamp_string)
from volttron.platform.messaging import topics, headers as headers_mod
from volttron.platform.agent.base_market_agent import MarketAgent
from volttron.platform.agent.base_market_agent.poly_line import PolyLine
from volttron.platform.agent.base_market_agent.point import Point
from volttron.platform.agent.base_market_agent.buy_sell import BUYER
from volttron.platform.agent.base_market_agent.buy_sell import SELLER

from TNT_Version3.PyCode.helpers import *
from TNT_Version3.PyCode.measurement_type import MeasurementType
from TNT_Version3.PyCode.measurement_unit import MeasurementUnit
from TNT_Version3.PyCode.meter_point import MeterPoint
from TNT_Version3.PyCode.market_state import MarketState
from TNT_Version3.PyCode.TransactiveNode import TransactiveNode
from TNT_Version3.PyCode.neighbor_model import Neighbor
from TNT_Version3.PyCode.temperature_forecast_model import TemperatureForecastModel
from TNT_Version3.PyCode.vertex import Vertex
from TNT_Version3.PyCode.timer import Timer
from TNT_Version3.PyCode.tcc_model import TccModel
from TNT_Version3.PyCode.dummy_tcc_model import DummyTccModel
from TNT_Version3.PyCode.day_ahead_auction import DayAheadAuction
from TNT_Version3.PyCode.direction import Direction

from transactive_utils.models_frame import Model


__version__ = "0.2"

utils.setup_logging()
_log = logging.getLogger(__name__)


class Transactive(Model):
    def __init__(self, config_path, **kwargs):
        super(Transactive, self).__init__(**kwargs)
        self.default_config = {}
        self.vip.config.set_default("config", self.default_config)
        self.vip.config.subscribe(self.configure_main,
                                  actions=["NEW", "UPDATE"],
                                  pattern="config")
        model_config = {}
        Model.__init__(self, model_config, **kwargs)

    def configure_main(self, config_name, action, contents):
        config = self.default_config.copy()
        config.update(contents)
        if action == "NEW" or "UPDATE":
            model_config = config.get("models", {})
            Model.__init__(self, model_config)

    @Core.receiver("onstart")
    def starting_base(self, sender, **kwargs):
        """
        Startup method:
         - Setup subscriptions to  devices.
         - Setup subscription to building power meter.
        :param sender:
        :param kwargs:
        :return:
        """
        for device_topic in self.models:
            _log.debug("Subscribing to " + device_topic)
            self.vip.pubsub.subscribe(peer="pubsub", prefix=device_topic, callback=self.new_data)
        _log.debug("Subscribing to " + self.power_meter_topic)
        self.vip.pubsub.subscribe(peer="pubsub", prefix=self.power_meter_topic, callback=self.load_message_handler)

    def new_data(self, peer, sender, bus, topic, header, message):
        """
        :param peer:
        :param sender:
        :param bus:
        :param topic:
        :param headers:
        :param message:
        :return:
        """
        _log.info("Data Received for {}".format(topic))
        now = parse_timestamp_string(header[headers_mod.TIMESTAMP])
        data, meta = message
        if topic in self.model:
            self.model[topic].update_data(data, now)

    def publish_record(self, topic, message):
        headers = {headers_mod.DATE: format_timestamp(get_aware_utc_now())}
        message["TimeStamp"] = format_timestamp(self.current_time)
        self.vip.pubsub.publish("pubsub", topic, headers, message).get()


def main(argv=sys.argv):
    """Main method called by the aip."""
    try:
        utils.vip_main(Transactive)
    except Exception as exception:
        _log.exception("unhandled exception")
        _log.error(repr(exception))


if __name__ == "__main__":
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
