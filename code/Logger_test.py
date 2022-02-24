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


#Helper function to convert ADC output back into original voltage signal
def analog_to_pH(adc_output):
  ph_equivalent = (adc_output * float(1 / 32767) + 7.0)
  return ph_equivalent

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
    pH_output = chan0.value 
    print (pH_output)
    pH_value = pH_output
    new_log.append("{:>2.4f}".format(pH_value))
    new_log.append("{:>2.4f}".format(pH_output))
    
    #write results to log
    with open(file_name, 'a') as data_log:
        logwriter = csv.writer(data_log)
        logwriter.writerow(new_log)
    print ("Wrote Log: ", new_log)

    #sleep DELAY_INTERVAL in seconds 
    sleep(DELAY_INTERVAL)

