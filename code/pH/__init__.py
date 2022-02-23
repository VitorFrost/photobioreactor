'''!
  modded pH sensor from anyleaf
  
  Dependencies for sensors:
- Adafruit_ADS1x15
- w1thermsensor
'''

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, List, Union
import struct
from filterpy.kalman import KalmanFilter
from filterpy.common import Q_discrete_white_noise
from . import filter

#import sensors
from pioreactor.hardware import SCL, SDA
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import board
import busio

DISCRETE_PH_JUMP_THRESH = 0.2
# Compensate for temperature diff between readings and calibration.
PH_TEMP_C = -0.05694  # pH/(V*T). V is in volts, and T is in °C

class CalSlot(Enum):
    """Keeps our calibration organized, so we track when to overwrite."""
    ONE = auto()
    TWO = auto()
    THREE = auto()
@dataclass
class OnBoard:
    """Specify onboard or offboard temperature source."""

    pass


@dataclass
class OffBoard:
    temp: float


@dataclass
class CalPt:
    V: float
    pH: float
    T: float
    
@dataclass
class CalPtT:
    V: float
    T: float  # Temp in C

@dataclass
class PhSensor:
    """Represents a pH sensor, or more broadly, any ion-selective glass electrode sensor.
    The default calibration is only appropriate for pH."""
    adc: ADS
    filter: KalmanFilter
    dt: float
    last_meas: float  # To let discrete jumps bypass the filter.
    cal_1: CalPt
    cal_2: CalPt
    cal_3: Optional[CalPt]

    def __init__(self, i2c, dt: float, address: int=0x48):
        # `dt` is in seconds.
        adc = ADS.ADS1115(i2c, address=address)
        adc.gain = 1  # Set the ADC's voltage range to be +-2.048V.

        self.adc = adc
        self.filter = filter.create(dt)
        self.dt = dt  # Store for when we update the filter's Q.
        self.last_meas: 7.0
        self.cal_1 = CalPt(0., 7.0, 23.)
        self.cal_2 = CalPt(0.17, 4.0, 23.)
        self.cal_3 = None
    
    def predict(self) -> None:
        """Make a prediction using the Kalman filter. Not generally used
        directly."""
        self.filter.predict()
        
    def update(self, t: Union[OnBoard, OffBoard]) -> None:
        """Update the Kalman filter with a pH reading. Not generally used
        directly."""
        pH = self.read_raw(t)

        if abs(pH - self.last_meas) > DISCRETE_PH_JUMP_THRESH:
            self.filter.reset()

        self.filter.update(pH)

    def read(self, t: Union[OnBoard, OffBoard]) -> float:
        """Take a pH reading, using the Kalman filter. This reduces sensor 
        noise, and provides a more accurate reading. Optional parameter `t` allows
        you to pass a temp manually, eg from a temperature probe in the solution.
        Not passing this uses the on-chip temp sensor."""
        self.predict()
        self.update(t)
        # self.filter.x is mean, variance. We only care about the mean
        return self.filter.x[0][0]

    def read_raw(self, t: Union[OnBoard, OffBoard]) -> float:
        """Take a pH reading, without using the Kalman filter"""
        if isinstance(t, OnBoard):
            T = temp_from_voltage(AnalogIn(self.adc, ADS.P2).voltage)
        else:
            T = t.temp

        chan_ph = AnalogIn(self.adc, ADS.P0, ADS.P1)
        pH = ph_from_voltage(chan_ph.voltage, T, self.cal_1, self.cal_2, self.cal_3)

        self.last_meas = pH
        return pH

    def read_voltage(self) -> float:
        """Useful for getting calibration data"""
        return AnalogIn(self.adc, ADS.P0, ADS.P1).voltage

    def read_temp(self) -> float:
        """Useful for getting calibration data"""
        return temp_from_voltage(AnalogIn(self.adc, ADS.P2).voltage)

    def calibrate(
        self, slot: CalSlot, pH: float, t: Union[OnBoard, OffBoard]
    ) -> (float, float):
        """Calibrate by measuring voltage and temp at a given pH. Set the
        calibration, and return (Voltage, Temp). Optional parameter `t` allows
        you to pass a temp manually, eg from a temperature probe in the solution.
        Not passing this uses the on-chip temp sensor."""
        if isinstance(t, OnBoard):
            T = temp_from_voltage(AnalogIn(self.adc, ADS.P2).voltage)
        else:
            T = t.temp

        V = AnalogIn(self.adc, ADS.P0, ADS.P1).voltage
        pt = CalPt(V, pH, T)

        if slot == CalSlot.ONE:
            self.cal_1 = pt
        elif slot == CalSlot.TWO:
            self.cal_2 = pt
        else:
            self.cal_3 = pt

        print(f"Calibration voltage at pH {pH}, {T}°C: {V}V")
        print(
            "Calibration set. Store those values somewhere, and apply them in"
            f"future runs: `calibrate_all(CalPt({V}, {pH}, {T}), ...)`"
        )

        return V, T

    def calibrate_all(
        self, pt0: CalPt, pt1: CalPt, pt2: Optional[CalPt] = None
    ) -> None:
        self.cal_1 = pt0
        self.cal_2 = pt1
        self.cal_3 = pt2

    def reset_calibration(self):
        self.cal_1 = CalPt(0.0, 7.0, 23.0)
        self.cal_2 = CalPt(0.17, 4.0, 23.0)
        self.cal_3 = None
        
def lg(
    pt0: (float, float), pt1: (float, float), pt2: (float, float), X: float
) -> float:
    """Compute the result of a Lagrange polynomial of order 3.
Algorithm created from the `P(x)` eq
[here](https://mathworld.wolfram.com/LagrangeInterpolatingPolynomial.html)."""
    result = 0.0

    x = [pt0[0], pt1[0], pt2[0]]
    y = [pt0[1], pt1[1], pt2[1]]

    for j in range(3):
        c = 1.0
        for i in range(3):
            if j == i:
                continue
            c *= (X - x[i]) / (x[j] - x[i])
        result += y[j] * c

    return result


def ph_from_voltage(
    V: float, T: float, cal_0: CalPt, cal_1: CalPt, cal_2: Optional[CalPt],
) -> float:
    """Convert voltage to pH
    We model the relationship between sensor voltage and pH linearly
    using 2-pt calibration, or quadratically using 3-pt. Temperature
    compensated. Input `T` is in Celsius."""

    # We infer a -.05694 pH/(V*T) sensitivity linear relationship
    # (higher temp means higher pH/V ratio)
    T_diff = T - cal_0.T
    T_comp = PH_TEMP_C * T_diff  # pH / V

    if cal_2:
        result = lg((cal_0.V, cal_0.pH), (cal_1.V, cal_1.pH), (cal_2.V, cal_2.pH), V)
        return result + T_comp * V
    else:
        a = (cal_1.pH - cal_0.pH) / (cal_1.V - cal_0.V)
        b = cal_1.pH - a * cal_1.V
        return (a + T_comp) * V + b