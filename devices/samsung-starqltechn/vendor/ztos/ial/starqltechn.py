"""ztOSIAL backends for the Galaxy S9 (Snapdragon: SCV38, SM-G9600;
starqltechn), for what generic Linux does not cover the generic way.

Sensors1: the light, proximity and motion sensors are on the sensor DSP
(SLPI), not IIO devices. iio-sensor-proxy reaches them through libssc
(hexagonrpcd serves the DSP its files) and offers them on D-Bus
(net.hadess.SensorProxy); this backend reads them there, and falls back to
the generic IIO one for anything the proxy does not have.
"""
from ztos_ial.backends import NotSupported
from ztos_ial.backends import generic

PROXY = 'net.hadess.SensorProxy'
PATH = '/net/hadess/SensorProxy'
G = 9.81
# the proxy gives the accelerometer only as which edge is up: the vector of
# gravity for each, in the phone's axes (x right, y up, z out of the screen)
ORIENTATION = {
    'normal': (0.0, G, 0.0), 'bottom-up': (0.0, -G, 0.0),
    'left-up': (-G, 0.0, 0.0), 'right-up': (G, 0.0, 0.0),
}


class Sensors(generic.Sensors):
    def __init__(self, config, manifest):
        super().__init__(config, manifest)
        self._proxy = None
        self._claimed = set()

    def _sensor_proxy(self):
        if self._proxy is None:
            try:
                from gi.repository import Gio
                self._proxy = Gio.DBusProxy.new_for_bus_sync(
                    Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None, PROXY, PATH, PROXY, None)
            except Exception:
                return None
        return self._proxy

    def _has(self, what):
        proxy = self._sensor_proxy()
        value = proxy.get_cached_property('Has' + what) if proxy else None
        return bool(value.unpack()) if value is not None else False

    def _claim(self, what):
        if what in self._claimed:
            return
        self._sensor_proxy().call_sync('Claim' + what, None, 0, 5000, None)
        self._claimed.add(what)

    def _value(self, name, default=None):
        proxy = self._sensor_proxy()
        value = proxy.get_cached_property(name) if proxy else None
        return value.unpack() if value is not None else default

    def _proxied(self):
        found = []
        for sensor, what in (('light', 'AmbientLight'), ('proximity', 'Proximity'),
                             ('accelerometer', 'Accelerometer')):
            if self._has(what):
                found.append(sensor)
        return found

    def available(self):
        return bool(self._proxied()) or super().available()

    def props(self):
        return {'Available': sorted(set(self._proxied()) | set(super().props()['Available']))}

    def m_Read(self, sensor):
        try:
            if sensor == 'light' and self._has('AmbientLight'):
                self._claim('Light')
                level = float(self._value('LightLevel', 0.0))
                # "vendor" units are a raw scale; only lux is what Read promises
                if self._value('LightLevelUnit', 'lux') != 'lux':
                    raise NotSupported('light: the sensor reports no lux')
                return [level]
            if sensor == 'proximity' and self._has('Proximity'):
                self._claim('Proximity')
                return [0.0 if self._value('ProximityNear', False) else 5.0]
            if sensor == 'accelerometer' and self._has('Accelerometer'):
                self._claim('Accelerometer')
                vector = ORIENTATION.get(self._value('AccelerometerOrientation', ''))
                if vector is None:
                    raise NotSupported('accelerometer: the phone is lying flat or the orientation is unknown')
                return list(vector)
        except NotSupported:
            raise
        except Exception as error:
            raise NotSupported(f'{sensor}: {error}') from None
        return super().m_Read(sensor)
