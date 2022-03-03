'''
Temporary logger for test purpose

Dependencies for sensors:
- Adafruit_ADS1x15
- w1thermsensor
'''

from time import sleep
import math
import csv
import os.path
from datetime import datetime


#import sensors
from pioreactor.hardware import SCL, SDA
from w1thermsensor import W1ThermSensor
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import board
import busio

# Create the I2C bus
i2c = busio.I2C(board.SCL, board.SDA)

#LOCAL VARIABLES
DATA_PATH = '/home/pi/datalogs' #data directory path
DATA_NAME = 'readings_logs' #data file name

now = datetime.now() #todays date
date_string = now.date().strftime("%Y_%m_%d")

DELAY_INTERVAL = 5

#Sensor Variables
temp_sensor = W1ThermSensor()
ads = ADS.ADS1115(i2c)
chan0 = AnalogIn(ads, ADS.P0)

#pH converter
DISCRETE_PH_JUMP_THRESH = 0.2
# Compensate for temperature diff between readings and calibration.
PH_TEMP_C = -0.05694  # pH/(V*T). V is in volts, and T is in °C
cal_1 = CalPt(3, 7.0, 23.0)
cal_2 = CalPt(2, 4.0, 23.0)
cal_3 = CalPt(4, 9.0, 23.0)

#Helper function to convert ADC output back into pH values
def analog_to_pH(
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
    result = lg((cal_0.V, cal_0.pH), (cal_1.V, cal_1.pH), (cal_2.V, cal_2.pH), V)
    ph_equivalent = result + T_comp * V
    return ph_equivalent

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

#create total file path (with date)
file_name = DATA_PATH + '/' + date_string + '_' + DATA_NAME

#if the file does not already exist, create a new file with csv headers
if not os.path.isfile(file_name):
    csv_headers = ['Date', 'Time','Temperature', 'pH', 'pH_RAW']
    with open(file_name, 'w') as new_data_file:
        datawriter = csv.writer(new_data_file)
        datawriter.writerow(csv_headers)

#main logging sequence
while True:
    new_log = []

    now = datetime.now()
    date_string = now.date().strftime("%Y_%m_%d")
    time_string = now.time().strftime("%H:%M:%S")
    
    new_log.append(date_string)
    new_log.append(time_string)

    #sensor1 
    temperature = temp_sensor.get_temperature()
    new_log.append("{:>2.2f}".format(temperature))
    
    #sensor2
    pH_output = chan0.voltage 
    print (pH_output)
    pH_value = analog_to_pH(pH_output, temperature, cal_1, cal_2, cal_3)
    new_log.append("{:>2.4f}".format(pH_value))
    new_log.append("{:f}".format(pH_output)
    
    #write results to log
    with open(file_name, 'a') as data_log:
        logwriter = csv.writer(data_log)
        logwriter.writerow(new_log)
    print ("Wrote Log: ", new_log)

    #sleep DELAY_INTERVAL in seconds 
    sleep(DELAY_INTERVAL)

