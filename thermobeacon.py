#!/usr/bin/python3 -u
# thermobeacon.py - Simple bluetooth LE scanner and data extractor

import sys
print(sys.path)

import mysql.connector
print("Datenbankverbindung wird hergestellt...") 
mydb = mysql.connector.connect(user='pi', password='mypassword', host='127.0.0.1', database='smarthome')
print("Verbindung erfolgreich hergestellt!")
mycursor = mydb.cursor()


from bluepy.btle import Scanner, DefaultDelegate # pylint: disable=import-error
from time import strftime
import struct

do_mqtt = False  # True
if do_mqtt:
	import paho.mqtt.client as mqtt
	mqttBroker ="pi3a2.rghome.local"
	mqclient = mqtt.Client("Bluetooth_Monitor")
	mqclient.connect(mqttBroker)


#Enter the MAC address of the sensors
SENSORS = {"1a:02:00:00:0d:ae": "Schreibtisch", "1a:02:00:00:0a:8c" : "Küche", "be:25:00:00:13:24" : "Nr. 3", "be:25:00:00:07:2e" : "Nr. 4"}

class DecodeErrorException(Exception):
     def __init__(self, value):
         self.value = value
     def __str__(self):
         return repr(self.value)

class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)

    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            #print ("Discovered device", dev.addr)
            pass
        elif isNewData:
            #print ("Received new data from", dev.addr)
            pass

def write_temp(where,what,value):
	with open("data.csv", "a") as log:
		log.write("{0}:00,{1},{2},{3}\n".format(strftime("%Y-%m-%d %H:%M"),where,what,value))

def convert_uptime(t):
    # convert seconds to day, hour, minutes and seconds
    days = t // (24 * 3600)
    t = t % (24 * 3600)
    hours = t // 3600
    t %= 3600
    minutes = t // 60
    t %= 60
    seconds = t
    return "{} Days {} Hours {} Minutes {} Seconds".format(days,hours,minutes,seconds)

#print("Establishing scanner...")
scanner = Scanner().withDelegate(ScanDelegate())

print ("-----------------------------------------------------------")
print (strftime("%Y-%m-%d %H:%M"))

#How many times should we try the device scan to find all the sensors?
retry_count = 30

sampled = {}
try:
    while (retry_count > 0 and len(sampled) < len(SENSORS)):
        print ("Initiating scan...")
        devices = scanner.scan(4.0)

        retry_count -= 1

        for dev in devices:
            print ("dev in devices: ", dev.addr)
            if dev.addr in SENSORS and not dev.addr in sampled:
                print ("Device %s (%s), RSSI=%d dB" % (dev.addr, dev.addrType, dev.rssi))
                CurrentDevAddr = dev.addr
                CurrentDevLoc = SENSORS[dev.addr]
                manufacturer_hex = next(value for _, desc, value in dev.getScanData() if desc == 'Manufacturer')
                print("manufacturer_hex = %s", manufacturer_hex)
                manufacturer_bytes = bytes.fromhex(manufacturer_hex)

                if len(manufacturer_bytes) == 20:
                    e6, e5, e4, e3, e2, e1, voltage, temperature_raw, humidity_raw, uptime_seconds = struct.unpack('xxxxBBBBBBHHHI', manufacturer_bytes)

                    temperature_C = temperature_raw / 16.
                    temperature_F = temperature_C * 9. / 5. + 32.

                    humidity_pct = humidity_raw / 16.

                    voltage = voltage / 1000

                    uptime = convert_uptime(uptime_seconds)

                    uptime_days = uptime_seconds / 86400

                    print ("Device: {} Temperature: {} degC Humidity: {}% Uptime: {} sec Voltage: {}V".format(CurrentDevLoc,temperature_C,humidity_pct,uptime,voltage))
                    write_temp(CurrentDevLoc,"Temperature",temperature_C)
                    write_temp(CurrentDevLoc,"Humidity",humidity_pct)
                    write_temp(CurrentDevLoc,"Voltage",voltage)
                    write_temp(CurrentDevLoc,"UpTime",uptime_days)
                    sampled[CurrentDevAddr] = True

                    # Und jetzt ab in die MariaDB-Datenbank schreiben
                    
                    # Temperatur
                    sql = """CALL AddSensorData('{}', '{}', {})""".format(dev.addr, 'Temperatur', temperature_C)
                    mycursor.execute(sql)
                    mydb.commit()
                    
                    # Humdity
                    sql = """CALL AddSensorData('{}', '{}', {})""".format(dev.addr, 'Luftfeuchtigkeit', humidity_pct)
                    mycursor.execute(sql)
                    mydb.commit()
                    
                    # Uptime
                    sql = """CALL AddSensorData('{}', '{}', {})""".format(dev.addr, 'Uptime', uptime_seconds)
                    mycursor.execute(sql)
                    mydb.commit()
                    
                    # Voltage
                    sql = """CALL AddSensorData('{}', '{}', {})""".format(dev.addr, 'Spannung', voltage)
                    mycursor.execute(sql)
                    mydb.commit()

                    print(mycursor.rowcount, "record inserted.")

                    if do_mqtt:
                        try:
                            mqclient.publish(CurrentDevLoc,temperature_C)
                        except Exception as e:
                            print ("MQ send failed: {}".format(e))

                else:
                    print ("Ignoring invalid data length for {}: {}".format(CurrentDevLoc,len(manufacturer_bytes)))

except DecodeErrorException:
    print("Decode Exception")
    pass

print ("-----------------------------------------------------------")


