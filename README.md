# ttn-ubirch-connector
- A tool written in Python to connect certain TTN applications to the UBirch backend
- The connector can only process data sent in a format like it is by the Kellsersensor

## Start
- The connector can be started by running
	```
	python ttn_connector.py
	```

## Dependencies
```
ttn
requests
msgpack
json_logging
```

## Configuration
- Config is done via a JSON file
- Where to locate this file is specified in `ttn_connector.py`
	```python
	...
	CONFIGFILE = "config.json"
	...
	```
- Here is the skelleton of this file
	```json
	{
		"LogConfig": {
			"logLevel": 10,
			"logFile": "/dev/stdout",
			"enableJSON": true,
			"logFormat": "[%(asctime)s]--[%(levelname)-8s]  %(message)s"
		},
		"OPConfig": {
			"disableUbirch": false,
			"showPing": false,
			"showMeasurements": true,
			"tickPeriod": 10
		},
		"TTNAppConfig": {
			"appID": "TTN_APP_ID",
			"appAccessKey": "TTN_APP_ACCESS_KEY"
		},
		"TTNDeviceConfig": {
			"allowedMessageDelay": 30,
			"allowedClockOffset": 30
		},
		"DataConfig": {
			"structFormat": "ffiii",
			"dataLayout": [
				"H",
				"T",
				"L_blue",
				"L_red",
				"time"
			]
		},
		"UbirchHTTPConfig": {
			"UbirchENV": "UBIRCH_ENV",
			"UbirchPASS": "UBIRCH_PASS",
			"UbirchKEY": "https://key.%s.ubirch.com/api/keyService/v1/pubkey/mpack",
			"UbirchDATA": "https://data.%s.ubirch.com/v1/json",
			"UbirchNIOMON": "https://niomon.%s.ubirch.com/",
			"HTTPPostTimeout": 5,
			"HTTPPostAttempts": 3
		}
	}
	```

### `"LogConfig"`
- #### `"LogLevel"`
	- normal `logging` log-level
	- one of the following
	```python
	10 - DEBUG
	20 - INFO
	30 - WARNING
	40 - ERROR
	50 - CRITICAL
	```
- #### `"logFile"`
	- path of the file to log into ... examples:
	```python
	"/dev/stdout"     - log to standard output
	"/dev/sdterr"     - log to error output
	"/dev/null"       - log into null (effectively disables logging)
	"/tmp/output.log" - Log into /tmp/output.log

	Or any other file path
	```
- #### `"enableJSON"`
	- enables/disables logging in JSON format
	```
	true  - enables logging in JSON format ("logFormat" will be ignored)
	false - disables logging in JSON format ("logFormat" will be used for formatting)
	```

### `"OPConfig"`
- #### `"disableUbirch"`
	- enables/disables passing data onto UBirch
- #### `"showPing"`
	- disables/enables showing pings sent from sensors
- #### `"showMeasurements"`
	- disables/enables showing measurements received from sensors
- #### `"tickPeriod"`
	- how often one tick will be performed (to check timers etc.

### `"TTNAppConfig"`
- both can be copied from the TTN console
- #### `"appID"`
	- ID of the TTN application
- #### `"appAccessKey"`
	- access key for the TTN application

### `"TTNDeviceConfig"`
- #### `"allowedMessageDelay"`
	- controls how long to wait for a response from the device before logging a timeout message (int; seconds)
- #### `"allowedClockOffset"`
	- max. allowed offset of the sensors clock before a timesync message is sent (take delay into consideration, int; seconds)

### `"DataConfig"`
- #### `"structFormat"`
	- format of the datastruct (see [struct](https://docs.python.org/3.8/library/struct.html))
- #### `"dataLayout"`
	- mapping of the values contained in the data struct, for exmaple:
	```python
	[
		"humidity",
		"temperature",
		"time"
	]
	```
	- the first element of the datastruct will be stored as `"humidity"` in the JSON object sent to Ubirch
	- the seconds element will be named temperature
	- **NOTE** that every data struct should contain a `"time"` element; time should be stored in seconds (UNIX-time)

### `"UbirchHTTPConfig"`
- #### `"UbirchENV"`
	- the UBirch environment to be used ... one of
	```python
		"dev"
		"demo"
		"prod"
	```
- #### `"UbirchPASS"`
	- access key to the UBirch API
- #### `"UbirchKEY"`
	- URL to send pubkey registration messages to
- #### `"UbirchDATA"`
	- URL of the UBirch data service
- #### `"UbirchNIOMON"`
	- URL of the UBirch signature validation service
- #### `"HTTPPostTimeout"`
	- max. allowed HTTP postout in seconds (int)
- #### `"HTTPPostAttempts"`
	- max. HTTP post retries