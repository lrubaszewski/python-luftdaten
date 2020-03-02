"""Wrapper to get the measurings from a Luftdaten station."""
import asyncio
import logging

import aiohttp
import async_timeout

from . import exceptions

_LOGGER = logging.getLogger(__name__)

_RESOURCE = 'https://api.luftdaten.info/v1'
_PUSH_ENDPOINT = "http://api.luftdaten.info/v1/push-sensor-data/"

SENSOR_SDS011  = 1    # value_types: P1 (PM10), P2 (PM2.5)
SENSOR_BMP180  = 3    # value_types: temperature, pressure
SENSOR_BME280  = 11   # value_types: temperature, humidity, pressure
SENSOR_PMS1003 = 1    # value_types: P1 (PM10), P2 (PM2.5)
SENSOR_PMS3003 = 1    # value_types: P1 (PM10), P2 (PM2.5)
SENSOR_PMS5003 = 1    # value_types: P1 (PM10), P2 (PM2.5)
SENSOR_PMS7003 = 1    # value_types: P0 (PM1), P1 (PM10), P2 (PM2.5)

class LuftdatenPush(object):
    """A class for handling the data pushing.
       source:
         https://github.com/opendata-stuttgart/meta/wiki/APIs#api-luftdateninfo
    """
    
    def __init__(self, sensor_type, chip_id, sw_version, loop, session):
        """Initialize the connection.
           sensors:
                SENSOR_SDS011 
                SENSOR_BMP180 
                SENSOR_BME280 
                SENSOR_PMS1003
                SENSOR_PMS3003
                SENSOR_PMS5003
                SENSOR_PMS7003
        """
        self._loop = loop
        self._session = session
        self.chip_id = chip_id
        self.sw_version = sw_version
        self.data = None
        self.values = {}
        self.meta = {}
        self.url = '{}'.format(_PUSH_ENDPOINT)
        self.headers = {
            'content-type': 'application/json',
            'X-Pin' : '%s' % format(sensor_type),
            'X-Sensor': self.chip_id
        }

    """
    Header:
        Content-Type: application/json  
        X-Pin: <n> 
        X-Sensor: <chip_id, eg. esp8266-12345678>
    Data:

    SDS011
        X-Pin: 1  
        value_types: P1 (PM10), P2 (PM2.5);
    BMP180:
        X-Pin: 3
        value_types: temperature, pressure;
    BME280:
        X-Pin: 11
        value_types: temperature, humidity, pressure; 
    PMS1003 - PMS 7003:
        X-Pin: 1
        value_types: P1 (PM10), P2 (PM2.5);

    """
    async def push_data(self, data):
        """Push the data.

           data:
               Dictionaries of results delivered by sensor
               format:
                {
                    "data_type" : "value", 
                    "data_type" : "value"
                }
               data types:
               temperature, humidity, pressure, P1, P2
        """
        try:
            sensordatavalues = []
            for key in data:
                sensordatavalues.append({"value_type":key,"value":data[key]})
            payload = {
                "software_version": self.sw_version, 
                "sensordatavalues": sensordatavalues
            }
            _LOGGER.debug("headers: %s" % str(self.headers))
            _LOGGER.debug("payload: %s" % str(payload))
            
            _LOGGER.debug(
                "Pushing data to luftdaten.info: %s", self.url)
            with async_timeout.timeout(60, loop=self._loop):
                response = await self._session.request('POST', self.url, json=payload, headers=self.headers)

            _LOGGER.debug(
                "Response from luftdaten.info: %s content_type %s", response.status, response.content_type)
            if response.content_type == 'text/html':
                text = await response.text()
                _LOGGER.debug("Response text: %s", text)
            elif response.content_type == 'application/json':
                json = await response.json()
                _LOGGER.debug(json)
        except (asyncio.TimeoutError, aiohttp.ClientError):
            _LOGGER.error("Can not load data from luftdaten.info")
            raise exceptions.LuftdatenConnectionError()

class Luftdaten(object):
    """A class for handling the data retrieval."""

    def __init__(self, sensor_id, loop, session):
        """Initialize the connection."""
        self._loop = loop
        self._session = session
        self.sensor_id = sensor_id
        self.data = None
        self.values = {}
        self.meta = {}
        self.url = '{}/{}'.format(_RESOURCE, 'sensor')
    
    async def get_data(self):
        """Retrieve the data."""
        try:
            url = '{}/{}/'.format(self.url, self.sensor_id)
            _LOGGER.debug(
                "Requesting luftdaten.info: %s", url)
            with async_timeout.timeout(60, loop=self._loop):
                response = await self._session.get(url)

            _LOGGER.debug(
                "Response from luftdaten.info: %s type %s", response.status, response.content_type)
            self.data = await response.json()
            _LOGGER.debug(self.data)
        except (asyncio.TimeoutError, aiohttp.ClientError):
            _LOGGER.error("Can not load data from luftdaten.info")
            raise exceptions.LuftdatenConnectionError()

        if not self.data:
            for measurement in self.values.keys():
                self.values[measurement] = None
            return

        try:
            sensor_data = sorted(
                self.data, key=lambda timestamp: timestamp['timestamp'],
                reverse=True)[0]

            for entry in sensor_data['sensordatavalues']:
                if entry['value_type'] not in self.values.keys():
                    self.values[entry['value_type']] = None
                for measurement in self.values.keys():
                    if measurement == entry['value_type']:
                        self.values[measurement] = float(entry['value'])

            self.meta['sensor_id'] = self.sensor_id
            self.meta['longitude'] = float(
                sensor_data['location']['longitude'])
            self.meta['latitude'] = float(sensor_data['location']['latitude'])
        except (TypeError, IndexError):
            raise exceptions.LuftdatenError()

    async def validate_sensor(self):
        """Return True if the sensor ID is valid."""
        return True if self.data else False

