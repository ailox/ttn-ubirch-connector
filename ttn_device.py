import requests
import mprotocol
import time

# helper function to assemble array of arrays into one array (ignoring the first byte of every subarray)
def reassemble(arr):
    if len(arr) == 0:
        return bytes([])
    else:
        return arr[0][1:] + reassemble(arr[1:])

class TTNDevice():
    """ A class storing information about a TTNDevice """

    def __init__(self, context, deviceID):
        self.context = context
        self.deviceID = deviceID
        self.received_registration_parts = []
        self.registration_upp = None
        self.stats = {
            # Number of measurements received since last timesync
            "totalMeasurements": 0,
            "measurementsSinceTimesync": 0,
            "runningOnBattery": False,  # if the device runs on battery
            "lastBatteryWarningT": 0,
            "uplinksReceived": 0,  # how many messages the device sent
            "downlinksSent": 0,  # how many messages were sent to the device
            "pendingAckT": 0,  # When an acknowledge is awaited
            "pendingDataResponseT": 0,  # When the next data response is awaited
            "pendingMeasurementT": 0,  # When the next measurement is awaited
            "execOnAck": None,  # Can hold a function to be exectured on next ack
            "lastMeasurement": {}
        }

        return

    # To be called when the device sends a ping
    def ping(self):
        if self.context.config["OPConfig"]["showPing"]:
            self.context.log.debug("[DEV:%s] ping received" % self.deviceID)

    # To be called on every iteration in the main loop (see ttn_connector.py)
    def tick(self, noTimesync=True):
        if not noTimesync:
            self.__check_timesync()

        self.__check_ack_timed_out()
        self.__check_data_response_timed_out()
        self.__check_measurement_timed_out()
        self.__check_registration_upp()

    # Functions to get values from the local stats object #
    # Return statistics
    def getStats(self):
        return self.stats

    # Returns lastMeasurement
    def getLastMeasurement(self):
        return self.stats["lastMeasurement"]

    # Return the value of pendingAckT
    def get_ack_pending_t(self):
        return self.stats["pendingAckT"]

    # Return the value of pendingDataResponseT
    def get_dataresponse_pending_t(self):
        return self.stats["pendingDataResponseT"]

    # Return the value of pendingMeasurementT
    def get_measurement_pending_t(self):
        return self.stats["pendingMeasurementT"]

    # Retrun the value of runningOnBattery
    def get_running_on_battery(self):
        return self.stats["runningOnBattery"]

    # Get the allowed delay of an awaited message (based on inCMDMode)
    def __get_allowed_delay(self):
        return self.context.config["TTNDeviceConfig"]["allowedMessageDelay"]

    # Functions to set values in the local stats object #
    # Set the last received measurements + pendingMeasurementT will be reset
    def setMeasurement(self, measurements):
        self.context.log.info("[DEV:%s] measurements received" % self.deviceID)

        for i in range(0, len(self.context.config["DataConfig"]["dataLayout"])):
            if i >= len(measurements):
                break

            if self.context.config["OPConfig"]["showMeasurements"]:
                self.context.log.info(self.context.config["DataConfig"]["dataLayout"][i] + ": " + str(measurements[i]))

            self.stats["lastMeasurement"].update({
                self.context.config["DataConfig"]["dataLayout"][i]: measurements[i]
            })

        self.stats["pendingMeasurementT"] = 0
        self.stats["measurementsSinceTimesync"] += 1
        self.stats["totalMeasurements"] += 1

    # When called, pendingAckT will be reset
    def setAckReceived(self):
        self.context.log.debug("[DEV:%s] acknowledge received" % self.deviceID)
        self.stats["pendingAckT"] = 0

        # Check if there is a function to be executed
        if self.stats["execOnAck"]:
            self.context.log.debug(
                "[DEV:%s] executing registered onAck-function" % self.deviceID)

            try:
                # Call the callback
                self.stats["execOnAck"]()

                # Delete the callback
                self.stats["execOnAck"] = None
            except Exception as e:
                self.context.log.exception("[DEV:%s] executing onAck callback failed: "
                                           % self.deviceID, e)
        else:
            self.context.log.debug(
                "[DEV:%s] no function registered for incoming acks!" % self.deviceID)

    # When called, pendingAckT will be reset
    def setNackReceived(self):
        self.context.log.error("[DEV:%s] NOT-acknowledge received"
                               % self.deviceID)

    # When called, pendingDataResponseT will be reset
    def setDataResponseReceived(self, response):
        self.context.log.debug("[DEV:%s] data response received"
                               % self.deviceID)

    # Add a part to the received_registration_parts array
    def setRegistrationPartReceived(self, part):
        # check if the reset flag is set
        if part[0] &0b01000000 != 0:
            self.context.log.debug("[DEV:%s] received key regestration reset message"
                                   % self.deviceID)

            self.received_registration_parts = []

        self.context.log.debug("[DEV:%s] received key registration UPP part (part %d - %d bytes)"
                               % (self.deviceID, len(self.received_registration_parts), len(part[1:])))
        self.context.log.debug("%s" % str(part[1:]))

        # add it to the array
        self.received_registration_parts.append(part)

        # check if the current part has a set termination flag
        if part[0] & 0b10000000 != 0:
            # registration message complete
            self.context.log.info("[DEV:%s] received complete key registration UPP"
                                  % self.deviceID)
            self.context.log.debug("[DEV:%s] ordering message parts (%d parts)"
                                   % (self.deviceID, len(self.received_registration_parts)))

            # sort the parts
            ordered = sorted(self.received_registration_parts, key=lambda x: x[0] & 0b00111111)

            self.context.log.debug("[DEV:%s] putting all parts into one" % self.deviceID)

            # re-assemble the upp
            self.registration_upp = reassemble(ordered)

        return

    # Check if the devices clock is in sync
    def __check_timesync(self):
        if "time" in self.stats["lastMeasurement"].keys():
            if self.stats["measurementsSinceTimesync"] > 0:
                self.context.log.debug("[DEV:%s] checking the current time of the device - %d"
                                    % (self.deviceID, self.stats["lastMeasurement"]["time"]))

                # Check by how much the sensors time is off
                if abs(self.stats["lastMeasurement"]["time"] - time.time())\
                        > self.context.config["TTNDeviceConfig"]["allowedClockOffset"]:
                    # Time has to be synced
                    self.__timesync()

    # Check if the current pending ack has timed out
    def __check_ack_timed_out(self):
        if self.stats["pendingAckT"] != 0:
            if time.time() - self.stats["pendingAckT"] > 0:
                self.context.log.warning(
                    "[DEV:%s] acknowledge timed out" % self.deviceID)

                # Reset pendingAckT
                self.stats["pendingAckT"] = 0

    # Check if the current pending data response timed out
    def __check_data_response_timed_out(self):
        if self.stats["pendingDataResponseT"] != 0:
            if time.time() - self.stats["pendingDataResponseT"] > 0:
                self.context.log.warning("[DEV:%s] data response timed out by %d seconds ..."
                                         % (self.deviceID, time.time() - self.stats["pendingDataResponseT"]))

            # Reset pendingAckT
            self.stats["pendingAckT"] = 0

    # Check if the current pending measurement timed out
    def __check_measurement_timed_out(self):
        if self.stats["pendingMeasurementT"] != 0 and not self.stats["inCMDMode"]:
            if time.time() - self.stats["pendingMeasurementT"] > 0:
                self.context.log.warning("[DEV:%s] measurement timed out by %d seconds ..."
                                         % (self.deviceID, time.time() - self.stats["pendingMeasurementT"]))

            # Reset pendingAckT
            self.stats["pendingAckT"] = 0

    # check if there is a complete key registration upp available
    def __check_registration_upp(self):
        if self.registration_upp != None:
            self.__register_device()

    # Functions that communicate with the device #
    # Send the device key registration upp
    def __register_device(self):
        self.context.log.info("[DEV:%s] sending the key registration upp to Ubirch"
                      % self.deviceID)

        self.context.log.debug("[DEV:%s] registration upp: %s (%d bytes)"
                                % (self.deviceID, str(self.registration_upp), len(self.registration_upp)))

        # send the request
        r = requests.post((self.context.config["UbirchHTTPConfig"]["UbirchKEY"] % self.context.config["UbirchHTTPConfig"]["UbirchENV"]),
                          headers={'Content-Type': 'application/octet-stream'},
                          data=self.registration_upp)

        # evaluate if success or not
        if r.status_code == 200:
            r.close()
            self.context.log.info("[DEV:%s] registration succeeded" % self.deviceID)
        else:
            self.context.log.error("[DEV:%s] registration failed: %s (%d)" % (self.deviceID, r.text, r.status_code))

        # delete the upp
        self.registration_upp = None

    # Send a timesync message to the device to set its time
    def __timesync(self):
        self.context.log.info("[DEV:%s] the sensors clock is off by %d seconds - synchronizing"
                              % (self.deviceID, abs(self.stats["lastMeasurement"]["time"] - time.time())))

        # Create the timesync message
        msg = {}
        msg["MSG_CTRL_B"] = mprotocol.MP_CTRL_B_TYPES["MSG_CTRL_TIMESYNC"]
        # try to compensate airtime by adding two seonds
        msg["MSG_DATA"] = round(time.mktime(time.localtime())) + 2

        # Send the message
        self.context.mqtt.send(self.deviceID, mprotocol.mk_mp_msg(msg))

        self.context.log.debug("[DEV:%s] timesync ctrl message sent - ack pending"
                               % self.deviceID)

        # Set the pendingAckT to in currenttime + allowedMessageDelay
        self.stats["pendingAckT"] = time.time()\
            + self.__get_allowed_delay()

        # Reset measurements since timesync
        self.stats["measurementsSinceTimesync"] = 0

    # Send a restart message to the device
    def __restart_device(self):
        self.context.log.info("[DEV:%s] sending restart command to the device"
                              % self.deviceID)

        # Create the restart message
        msg = {}
        msg["MSG_CTRL_B"] = mprotocol.MP_CTRL_B_TYPES["MSG_CTRL_RESTART"]

        # Send the message
        self.context.mqtt.send(self.deviceID, mprotocol.mk_mp_msg(msg))

        # Reset all pendings
        self.stats["pendingAckT"] = 0
        self.stats["pendingDataResponseT"] = 0
        self.stats["pendingMeasurementT"] = 0

        # Set pendingAckT because the device has to acknowledge the command
        self.stats["pendingAckT"] = time.time()\
            + self.__get_allowed_delay()

        self.context.log.debug("[DEV:%s] restart ctrl message sent - ack pending"
                               % self.deviceID)

        # install the acknowledge callback
        def onAck():
            self.context.log.info("[DEV:%s] device restarting" % self.deviceID)

        self.stats["execOnAck"] = onAck

    # Commands the device to load its original config
    def __restore_orig_config(self):
        self.context.log.info("[DEV:%s] sending load original config command to the device"
                              % self.deviceID)

        # Create the restart message
        msg = {}
        msg["MSG_CTRL_B"] = mprotocol.MP_CTRL_B_TYPES["MSG_CTRL_RESTORE_ORIG_CONFIG"]

        # Send the message
        self.context.mqtt.send(self.deviceID, mprotocol.mk_mp_msg(msg))

        # Set pendingAckT because the device has to acknowledge the command
        self.stats["pendingAckT"] = time.time()\
            + self.__get_allowed_delay()

        self.context.log.debug("[DEV:%s] load original config ctrl message sent - ack pending"
                               % self.deviceID)

        # install the acknowledge callback
        def onAck():
            self.context.log.info(
                "[DEV:%s] original config loaded" % self.deviceID)
            self.stats["inCMDMode"] = False

        self.stats["execOnAck"] = onAck

    # Commands the device to send a config value
    def __read_cfg_val(self, id):
        self.context.log.info("[DEV:%s] sending read cfg val command to the device"
                              % self.deviceID)

        # Create the restart message
        msg = {}
        msg["MSG_CTRL_B"] = mprotocol.MP_CTRL_B_TYPES["MSG_CTRL_READ_CFG_VAL"]
        msg["MSG_DATA"] = id

        # Send the message
        self.context.mqtt.send(self.deviceID, mprotocol.mk_mp_msg(msg))

        # Set pendingAckT because the device has to acknowledge the command
        self.stats["pendingDataResponse"] = time.time()\
            + self.__get_allowed_delay()

        self.context.log.debug("[DEV:%s] read cfg val ctrl message sent - data response pending"
                               % self.deviceID)

    # Commands the device to send a config value
    def __set_cfg_val(self, id, value):
        self.context.log.info("[DEV:%s] sending set cfg val command to the device"
                              % self.deviceID)

        # Create the restart message
        msg = {}
        msg["MSG_CTRL_B"] = mprotocol.MP_CTRL_B_TYPES["MSG_CTRL_SET_CFG_VAL"]
        msg["MSG_DATA"] = [id, value]

        # Send the message
        self.context.mqtt.send(self.deviceID, mprotocol.mk_mp_msg(msg))

        self.context.log.debug("[DEV:%s] set cfg val ctrl message sent - data response pending"
                               % self.deviceID)

        # install the acknowledge callback
        def onAck():
            self.context.log.info("[DEV:%s] cfg val set" % self.deviceID)

        self.stats["execOnAck"] = onAck
