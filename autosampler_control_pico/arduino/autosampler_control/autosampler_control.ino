#include <LittleFS.h>
#include <ArduinoJson.h>

#include <Wire.h>
#include <math.h>
#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/bootrom.h"

#include "helpers.h"

#define LED_PIN LED_BUILTIN
#define RAMP_SIZE 200

// const are default values
const float version = 1.1; // Version of the autosampler control software
bool DEBUG = false;        // Set to true to enable debug messages
const char STANDARD_DELIMITER = ':';
const int MAX_BUFFER_SIZE = 300;      // Maximum buffer size for input string
const int BAUD_RATE = 115200;         // Baud rate for serial communication
String inputString = "";              // a string to hold incoming data
volatile bool stringComplete = false; // whether the string is complete
// Default Pin definitions
const int DEFAULT_PULSE_PIN = 12;
const int DEFAULT_DIRECTION_PIN = 14;
const int DEFAULT_ENABLE_PIN = 15;
// Pin definitions for the AS5600 magnetic encoder
const int ENCODER_SDA_PIN = 6;
const int ENCODER_SCL_PIN = 7;
const int ENCODER_PGO_PIN = 8;
const int ENCODER_DIR_PIN = 9;
const int ENCODER_ADDR = 0x36;
uint8_t encoderReadBuffer[2]; // Enough for max 2-byte read
uint16_t lastAngle = 0;
uint8_t lastAGC, lastStatus = 0;
uint8_t encoderWriteBuffer = 0x0E; // Register to read the angle

bool HOLDING = false;            // Flag to indicate if the motor is holding
bool blinkLED = false;           // Flag to indicate if the LED should blink
unsigned long lastBlinkTime = 0; // Last time the LED was blinked
const int BLINK_INTERVAL = 200;  // Interval for LED blinking in milliseconds
// Position limit
const int MIN_POSITION = 0;
const int MAX_POSITION = 16000;

// Ramp profile
int rampProfile[RAMP_SIZE] = {};
int ramp_max_interval = 3000;
int ramp_min_interval = 1000;
float ramp_curve_scale = 3.0f; // Controls steepness of the transition
float ratio = 1.0;             // A global scale factor applied to the ramp profile intervals
float dutyCycle = 0.5;         // Duty cycle for the PWM signal

class Autosampler
{
private:
    int pulsePin = DEFAULT_PULSE_PIN;
    int directionPin = DEFAULT_DIRECTION_PIN;
    int enablePin = DEFAULT_ENABLE_PIN;

    bool isPoweredOn = false;
    int currentPosition = 0;
    int failSafePosition = 0;
    bool currentDirection = true; // true: left, false: right

    int minPosition = MIN_POSITION;
    int maxPosition = MAX_POSITION;
    volatile bool moveInProgress = false;
    volatile bool stopRequested = false;
    volatile int stepsTaken = 0;
    volatile int stepsRemaining = 0;
    unsigned long moveStartTime = 0;
    unsigned long lastUpdateTime = 0;

    String name = "Not Set"; // Name of the autosampler

    JsonDocument slotsConfig;  // JSON object to store slot positions
    JsonDocument globalConfig; // JSON object to store global configuration
    void stopMovementWrapUp()
    {
        if (moveInProgress)
        {
            moveInProgress = false;
            stopRequested = false;
            stepsTaken = 0;
            stepsRemaining = 0;
            lastUpdateTime = 0;

            saveConfiguration();
            enableStepper(HOLDING);
            double timeTaken = (micros() - moveStartTime) / 1e6;
            Serial.printf("INFO: Movement completed, total time taken: %fs, currentPosition=%d\n", timeTaken, currentPosition);
        }
    }
    void enableStepper(bool enable)
    {
        digitalWrite(enablePin, enable ? LOW : HIGH); // LOW enables driver
        isPoweredOn = enable;
    }
    int getStepInterval()
    {
        int interval;

        if (stepsTaken < RAMP_SIZE)
        {
            // Ramp-up phase
            interval = rampProfile[stepsTaken];
        }
        else if (stepsRemaining <= RAMP_SIZE)
        {
            // Ramp-down phase
            interval = rampProfile[stepsRemaining - 1];
        }
        else
        {
            // Constant (steady) speed
            interval = rampProfile[RAMP_SIZE - 1];
        }

        return int(interval * ratio);
    }
    void saveConfiguration(bool initialValues = false)
    {
        // Save the current position and direction to the configuration file
        File configFile = LittleFS.open("/config.json", "w");
        if (!configFile)
        {
            Serial.println("ERROR: Unable to open configuration file.");
            return;
        }
        if (initialValues)
        {
            Serial.println("INFO: initializing global configuration.");
            // save a default configuration
            globalConfig.clear();
            globalConfig["currentPosition"] = 0;
            globalConfig["currentDirection"] = true;
            globalConfig["pulsePin"] = DEFAULT_PULSE_PIN;
            globalConfig["directionPin"] = DEFAULT_DIRECTION_PIN;
            globalConfig["enablePin"] = DEFAULT_ENABLE_PIN;
            globalConfig["minPosition"] = MIN_POSITION;
            globalConfig["maxPosition"] = MAX_POSITION;
            globalConfig["Year"] = (int16_t)2025;
            globalConfig["Month"] = (int8_t)1;
            globalConfig["Day"] = (int8_t)1;
            globalConfig["Hour"] = (int8_t)0;
            globalConfig["Minute"] = (int8_t)0;
            globalConfig["Second"] = (int8_t)0;
            globalConfig["Dotw"] = (int8_t)3;
            globalConfig["debug"] = DEBUG;
            globalConfig["holding"] = HOLDING;
            globalConfig["name"] = "Not Set";
        }
        else
        {
            globalConfig["currentPosition"] = currentPosition;
            globalConfig["currentDirection"] = currentDirection;
            globalConfig["pulsePin"] = pulsePin;
            globalConfig["directionPin"] = directionPin;
            globalConfig["enablePin"] = enablePin;
            globalConfig["minPosition"] = minPosition;
            globalConfig["maxPosition"] = maxPosition;
            datetime_t datetime;
            rtc_get_datetime(&datetime);
            globalConfig["Year"] = datetime.year;
            globalConfig["Month"] = datetime.month;
            globalConfig["Day"] = datetime.day;
            globalConfig["Hour"] = datetime.hour;
            globalConfig["Minute"] = datetime.min;
            globalConfig["Second"] = datetime.sec;
            globalConfig["Dotw"] = datetime.dotw;
            globalConfig["debug"] = DEBUG;
            globalConfig["holding"] = HOLDING;
            globalConfig["name"] = name;
        }
        serializeJsonPretty(globalConfig, configFile);
        configFile.close();
        if (DEBUG)
        {
            Serial.printf("DEBUG: Configuration json saved: ");
            serializeJson(globalConfig, Serial);
            Serial.println();
        }
    }
    void loadConfiguration()
    {
        File file = LittleFS.open("/config.json", "r");
        if (file)
        {
            DeserializationError ERROR = deserializeJson(globalConfig, file);
            file.close();
            if (ERROR)
            {
                saveConfiguration(true);
            }
            else
            {
                currentPosition = globalConfig["currentPosition"].as<int>();
                currentDirection = globalConfig["currentDirection"].as<bool>();
                String direction = currentDirection ? "Left" : "Right";
                pulsePin = globalConfig["pulsePin"].as<int>();
                directionPin = globalConfig["directionPin"].as<int>();
                enablePin = globalConfig["enablePin"].as<int>();
                minPosition = globalConfig["minPosition"].as<int>();
                maxPosition = globalConfig["maxPosition"].as<int>();
                DEBUG = globalConfig["debug"].as<bool>();
                HOLDING = globalConfig["holding"].as<bool>();
                name = globalConfig["name"].as<String>();
                if (DEBUG)
                {
                    Serial.printf("DEBUG: Configuration json loaded: ");
                    serializeJson(globalConfig, Serial);
                    Serial.println();
                }
            }
        }
        else
        {
            saveConfiguration(true);
        }
    }
    void saveSlotsConfig(bool initialValues = false)
    {
        File file = LittleFS.open("/slots_config.json", "w");
        if (!file)
        {
            Serial.println("ERROR: Unable to open slots configuration file.");
            return;
        }
        if (initialValues)
        {
            Serial.println("INFO: initializing slots configuration.");
            // save a default configuration
            slotsConfig.clear();
            slotsConfig["waste"] = 0;
            slotsConfig["fail-safe"] = 0;
            slotsConfig["0"] = 0;
        }
        serializeJsonPretty(slotsConfig, file);
        file.close();
        if (DEBUG)
        {
            Serial.printf("DEBUG: Slots configuration saved: ");
            serializeJson(slotsConfig, Serial);
            Serial.println();
        }
    }
    void loadSlotsConfig()
    {
        File file = LittleFS.open("/slots_config.json", "r");
        if (file)
        {
            DeserializationError ERROR = deserializeJson(slotsConfig, file);
            file.close();
            if (ERROR)
            {
                saveSlotsConfig(true);
            }
            else
            {
                if (DEBUG)
                {
                    Serial.printf("DEBUG: Slots configuration loaded: ");
                    serializeJson(slotsConfig, Serial);
                    Serial.println();
                }
            }
        }
        else
        {
            saveSlotsConfig(true);
        }
    }

public:
    uint64_t currentTimestamp = 0;
    uint64_t lastTimestamp = 0;

    Autosampler() {}
    Autosampler(int pulsePin, int directionPin, int enablePin)
        : pulsePin(pulsePin),
          directionPin(directionPin),
          enablePin(enablePin) {}

    void begin()
    {
        loadConfiguration();
        loadSlotsConfig();
        failSafePosition = slotsConfig["fail-safe"].as<int>();

        setPin(pulsePin, directionPin, enablePin);
    }

    void moveToPosition(int position)
    {
        if (moveInProgress)
        {
            Serial.println("INFO: Movement already in progress, interrupting current movement...");
            stopMovementWrapUp();
        }
        position = constrain(position, minPosition, maxPosition);
        int steps = position - currentPosition;
        if (DEBUG)
        {
            Serial.printf("DEBUG: moveToPosition called with position=%d, steps=%d\n", position, steps);
        }
        if (steps == 0)
        {
            Serial.println("INFO: Already at the target position.");
            return;
        }

        currentDirection = (steps > 0);
        digitalWrite(directionPin, currentDirection ? HIGH : LOW);

        moveInProgress = true;
        stopRequested = false;
        stepsTaken = 0;
        stepsRemaining = abs(steps);
        lastUpdateTime = 0;

        enableStepper(true);
        moveStartTime = micros();
    }
    void updateMovement()
    {
        if (!moveInProgress)
        {
            return;
        }
        if (stopRequested)
        {
            stopMovementWrapUp();
            return;
        }

        unsigned long interval = getStepInterval();
        unsigned long currentTime = micros();
        if (currentTime < lastUpdateTime) // skip if the timer has overflowed
        {
            lastUpdateTime = currentTime;
            return;
        }
        if (currentTime - lastUpdateTime >= interval)
        {
            if (Wire1.finishedAsync())
            {
                encoderWriteBuffer = 0x0E; // Register to read the angle
                Wire1.writeReadAsync(ENCODER_ADDR, &encoderWriteBuffer, 1, encoderReadBuffer, 2, true);
            }
            if (DEBUG)
            {
                currentTimestamp = getCurrentTime();
                uint64_t elapsedTime = currentTimestamp - lastTimestamp;
                lastTimestamp = currentTimestamp;
                Serial.printf("DEBUG: One step taken, stepsTaken=%d, stepsRemaining=%d, currentPosition=%d, target interval=%luμs, actual elapsedTime=%luμs\n",
                              stepsTaken, stepsRemaining, currentPosition, interval, elapsedTime);
            }

            noInterrupts();
            digitalWrite(pulsePin, HIGH);
            lastUpdateTime = currentTime;
            interrupts();

            sleep_us((uint64_t)interval * dutyCycle);
            digitalWrite(pulsePin, LOW);
            stepsRemaining--;
            stepsTaken++;
            currentPosition += currentDirection ? 1 : -1;

            if (Wire1.finishedAsync())
            {
                uint16_t currentAngle = ((encoderReadBuffer[0] << 8) | encoderReadBuffer[1]) & 0x0FFF;
                // shortest angular distance
                uint16_t diff1 = (currentAngle - lastAngle + 4096) % 4096;
                uint16_t diff2 = (lastAngle - currentAngle + 4096) % 4096;
                uint16_t angleDiff = diff1 < diff2 ? diff1 : diff2;

                if (DEBUG)
                {
                    Serial.printf("DEBUG: Encoder angle=%d, angleDiff=%d", currentAngle, angleDiff);
                    Serial.println();
                }
                lastAngle = currentAngle;
            }

            if (stepsRemaining <= 0)
            {
                stopMovementWrapUp();
            }
        }
    }
    void stopMovement()
    {
        stopRequested = true;
    }
    int getCurrentPosition()
    {
        return currentPosition;
    }
    int setCurrentPosition(int position)
    {
        currentPosition = constrain(position, minPosition, maxPosition);
        saveConfiguration();
        return currentPosition;
    }
    String getCurrentDirection()
    {
        return currentDirection ? "Left" : "Right";
    }
    void setCurrentDirection(bool direction)
    {
        currentDirection = direction;
        saveConfiguration();
    }
    int getFailSafePosition()
    {
        return failSafePosition;
    }
    void setFailSafePosition(int position)
    {
        failSafePosition = constrain(position, minPosition, maxPosition);
        slotsConfig["fail-safe"] = failSafePosition;
        saveSlotsConfig();
    }
    void moveToSlot(String slot)
    {
        if (!slotsConfig[slot].is<JsonVariant>())
        {
            Serial.printf("ERROR: Slot %s not found.\n", slot.c_str());
            return;
        }
        int targetPosition = slotsConfig[slot].as<int>();
        Serial.printf("INFO: Moving to slot %s at position %d\n", slot.c_str(), targetPosition);
        moveToPosition(targetPosition);
    }
    void setSlotPosition(String slot, int position)
    {
        if (slotsConfig[slot].is<JsonVariant>())
        {
            Serial.printf("SUCCESS: Slot %s position updated to %d\n", slot.c_str(), position);
        }
        else
        {
            Serial.printf("SUCCESS: Slot %s position set to %d\n", slot.c_str(), position);
        }
        slotsConfig[slot] = constrain(position, minPosition, maxPosition);
        saveSlotsConfig();
    }
    void deleteSlot(String slot)
    {
        if (!slotsConfig[slot].is<JsonVariant>())
        {
            Serial.printf("ERROR: Slot %s not found.\n", slot.c_str());
            return;
        }
        if (slot.equalsIgnoreCase("fail-safe"))
        {
            Serial.println("ERROR: Cannot delete fail-safe slot.");
            return;
        }
        slotsConfig.remove(slot);
        saveSlotsConfig();
        Serial.printf("SUCCESS: Slot %s deleted.\n", slot.c_str());
    }
    void moveToLeftMost()
    {
        moveToPosition(maxPosition);
    }
    void moveToRightMost()
    {
        moveToPosition(minPosition);
    }
    void dumpSlotsConfig()
    {
        Serial.print("INFO: Slots configuration: ");
        serializeJson(slotsConfig, Serial);
        Serial.println();
    }
    void dumpGlobalConfig()
    {
        Serial.print("INFO: Global configuration: ");
        serializeJson(globalConfig, Serial);
        Serial.println();
    }
    datetime_t getDateTime()
    {
        datetime_t t = {
            .year = globalConfig["Year"],
            .month = globalConfig["Month"],
            .day = globalConfig["Day"],
            .dotw = globalConfig["Dotw"],
            .hour = globalConfig["Hour"],
            .min = globalConfig["Minute"],
            .sec = globalConfig["Second"]};
        return t;
    }
    void saveConfig()
    {
        saveConfiguration();
    }
    void assertHolding()
    {
        enableStepper(HOLDING);
    }
    bool setName(String newName)
    {
        if (newName.length() > 0 && newName.length() < 20)
        {
            name = newName;
            globalConfig["name"] = name;
            saveConfiguration();
            return true;
        }
        else
        {
            Serial.println("ERROR: Invalid name, must be between 1 and 20 characters.");
            return false;
        }
    }
    String getName()
    {
        return name;
    }
    // read from a memory location in the I2C device
    bool readI2C(int address, int reg, uint8_t *data, int length)
    {
        // Write the memory pointer
        Wire1.beginTransmission(address); // Send START + 7-bit address + Write bit (0)
        Wire1.write(reg);                 // Write the register address
        Wire1.endTransmission(false);     // Send repeated START

        // Read the data
        int bytesRead = Wire1.requestFrom(address, length, true);
        if (bytesRead != length)
        {
            Serial.printf("WARNING: Requested %d bytes but received %d bytes.\n", length, bytesRead);
            for (int i = 0; i < bytesRead; i++)
            {
                data[i] = 0; // Fill the remaining bytes with 0
            }
            return false;
        }

        for (int i = 0; i < bytesRead; i++)
        {
            data[i] = Wire1.read();
        }
        if (DEBUG)
        {
            Serial.printf("DEBUG: Read %d bytes from I2C address 0x%02X, register 0x%02X: ", bytesRead, address, reg);
            for (int i = 0; i < bytesRead; i++)
            {
                Serial.printf("0x%02X ", data[i]);
            }
            Serial.println();
        }
        return true;
    }
    // Asynchronous read for a memory location in the I2C device
    bool readI2CAsync(uint8_t address, uint8_t reg, uint8_t *data, size_t length)
    {
        if (!Wire1.finishedAsync()) // Ensure no async op is in progress
            return false;
        return Wire1.writeReadAsync(address, &reg, 1, data, length, true);
    }
    // read the values from the encoder and print it
    void readEncoder()
    {
        // make sure there no async operation in progress, then issue a regular read
        if (!Wire1.finishedAsync())
        {
            Serial.println("ERROR: Encoder read in progress, please wait.");
            return;
        }
        uint8_t ReadBuffer[2];
        readI2C(ENCODER_ADDR, 0x0E, ReadBuffer, 2);
        lastAngle = (((uint16_t)ReadBuffer[0] << 8) | (uint16_t)ReadBuffer[1]) & 0x0FFF;
        readI2C(ENCODER_ADDR, 0x1A, ReadBuffer, 1);
        lastAGC = ReadBuffer[0];
        readI2C(ENCODER_ADDR, 0x0B, ReadBuffer, 1);
        lastStatus = ReadBuffer[0];
        bool magnetDetect = (lastStatus & 0b00100000) != 0;    // Check if magnet is detected
        bool magnetTooWeak = (lastStatus & 0b00010000) != 0;   // Check if magnet is too weak
        bool magnetTooStrong = (lastStatus & 0b00001000) != 0; // Check if magnet is too strong
        Serial.printf("INFO: Encoder angle=%d, AGC=%d, Magnet Detect=%s, Magnet Too Weak=%s, Magnet Too Strong=%s\n",
                      lastAngle, lastAGC,
                      magnetDetect ? "Yes" : "No",
                      magnetTooWeak ? "Yes" : "No",
                      magnetTooStrong ? "Yes" : "No");
        Serial.println();
    }
    void blinkLEDTask()
    {
        if (blinkLED)
        {
            unsigned long currentMillis = millis();
            if (currentMillis - lastBlinkTime >= BLINK_INTERVAL)
            {
                lastBlinkTime = currentMillis;
                digitalWrite(LED_PIN, !digitalRead(LED_PIN)); // Toggle LED state
            }
        }
    }
    void setPin(int pulse, int direction, int enable)
    {
        pulsePin = pulse;
        directionPin = direction;
        enablePin = enable;
        pinMode(pulsePin, OUTPUT);
        pinMode(directionPin, OUTPUT);
        pinMode(enablePin, OUTPUT);
        digitalWrite(pulsePin, LOW);
        digitalWrite(directionPin, LOW);
        digitalWrite(enablePin, HOLDING ? LOW : HIGH); // LOW enables driver
        saveConfiguration();
    }
};

Autosampler autosampler;

// parse the input string, the format is <command>:<value1>:<value2>...
void parseInputString()
{
    inputString.trim(); // trim
    if (inputString.length() == 0)
    {
        Serial.println("ERROR: Empty command.");
        return;
    }
    // split the input string into values
    int index = 0;                                  // current character index
    int inputStringLength = inputString.length();   // length of the input string
    int maxArrayLength = inputStringLength / 2 + 1; // maximum number of arrays
    String values[maxArrayLength];                  // array to hold the values
    int valueCount = 0;                             // number of values parsed
    while (index < inputStringLength)
    {
        // find the next delimiter
        int delimiterIndex = inputString.indexOf(STANDARD_DELIMITER, index);
        if (delimiterIndex == -1)
        {
            values[valueCount++] = inputString.substring(index); // Take remainder of the string
            break;
        }
        else
        {
            values[valueCount++] = inputString.substring(index, delimiterIndex);
            index = delimiterIndex + 1; // move to the next character after the delimiter
        }
    }

    if (valueCount <= 0)
    {
        Serial.println("ERROR: Invalid command format, expected format is <command>:<value1>:<value2>...");
        return;
    }

    String command = values[0];

    if (DEBUG) // print back the parsed values
    {
        Serial.print("DEBUG: Command received: ");
        for (int i = 0; i < valueCount; i++)
        {
            Serial.print(values[i]);
            if (i < valueCount - 1)
            {
                Serial.print(", ");
            }
        }
        Serial.println();
    }

    if (command.equalsIgnoreCase("help"))
    {
        Serial.println("INFO: Autosampler control commands:");
        Serial.println("    help - Show this help message.");
        Serial.println("    ping - Check the connection to the autosampler.");
        Serial.println("    setPosition:<position> - Set the current position of the autosampler.");
        Serial.println("    getPosition - Get the current position of the autosampler.");
        Serial.println("    setDirection:<direction> - Set the direction of the autosampler (1 for left, 0 for right).");
        Serial.println("    getDirection - Get the current direction of the autosampler.");
        Serial.println("    getFailSafePosition - Get the fail safe position of the autosampler.");
        Serial.println("    setFailSafePosition:<position> - Set the fail safe position of the autosampler.");
        Serial.println("    moveTo:<position> - Move to a specific position.");
        Serial.println("    moveToLeftMost - Move to the left most position.");
        Serial.println("    moveToRightMost - Move to the right most position.");
        Serial.println("    stop - Stop the autosampler movement.");
        Serial.println("    moveToSlot:<slot> - Move to a specific slot.");
        Serial.println("    setSlotPosition:<slot>:<position> - Set the position of a slot.");
        Serial.println("    deleteSlot:<slot> - Delete the position of a slot.");
        Serial.println("    dumpSlotsConfig - Dump the slots configuration.");
        Serial.println("    dumpGlobalConfig - Dump the global configuration.");
        Serial.println("    stime:<year>:<month>:<day>:<hour>:<minute>:<second> - Set the RTC time on the device.");
        Serial.println("    time - Get the RTC time on the device.");
        Serial.println("    setRatio:<value> - Set the ratio for the stepper motor speed (default is 1).");
        Serial.println("    getRatio - Get the current ratio for the stepper motor speed.");
        Serial.println("    generateRampProfile - Regenerate the ramp profile for the stepper motor.");
        Serial.println("    setRampSteepness:<value> - Set the steepness of the ramp profile (default is 3.0).");
        Serial.println("    setRampMinInterval:<value> - Set the minimum interval for the ramp profile in us (default is 1000).");
        Serial.println("    setRampMaxInterval:<value> - Set the maximum interval for the ramp profile in us (default is 3000).");
        Serial.println("    set_name:<name> - Set the name of the autosampler.");
        Serial.println("    get_name - Get the name of the autosampler.");
        Serial.println("    readEncoder - Read the encoder value.");
        Serial.println("    debug - Enable or disable debug mode.");
        Serial.println("    queryDebug - Query the current debug mode status.");
        Serial.println("    holding - Enable or disable holding mode.");
        Serial.println("    queryHolding - Query the current holding mode status.");
        Serial.println("    blink_en - Enable or disable LED blinking.");
        Serial.println("    blink_dis - Disable LED blinking.");
        Serial.println("    bootsel - Enter BOOTSEL mode.");
        Serial.println("    setPin:<pulsePin>:<directionPin>:<enablePin> - Set the pins for the stepper motor control.");
        Serial.println("    reset - Reset the device.");
    }
    else if (command.equalsIgnoreCase("stop"))
    {
        autosampler.stopMovement();
    }
    else if (command.equalsIgnoreCase("moveTo"))
    {
        if (valueCount == 2)
        {
            int targetPosition = values[1].toInt();
            // check if position is a int using C++ method
            if (targetPosition == 0 && values[1] != "0")
            {
                Serial.println("ERROR: Invalid target position value, expected an integer.");
            }
            else
            {
                autosampler.moveToPosition(targetPosition);
            }
        }
        else
        {
            Serial.println("ERROR: Invalid command format, expected format is moveTo:<position>");
        }
    }
    else if (command.equalsIgnoreCase("ping"))
    {
        Serial.println("PING: Autosampler Control Version " + String(version));
    }
    else if (command.equalsIgnoreCase("stime")) // set the RTC time on device
    // format "stime:{now.year}:{now.month}:{now.day}:{now.dotw}:{now.hour}:{now.minute}:{now.second}"
    {
        if (valueCount == 8)
        {
            int year = values[1].toInt();
            int month = values[2].toInt();
            int day = values[3].toInt();
            int dotw = values[4].toInt();
            int hour = values[5].toInt();
            int minute = values[6].toInt();
            int second = values[7].toInt();
            setDateTime(year, month, day, dotw, hour, minute, second);
            autosampler.saveConfig();
        }
        else
        {
            Serial.println("ERROR: Invalid command format, expected format is stime:<year>:<month>:<day>:{now.dotw}:<hour>:<minute>:<second>");
        }
    }
    else if (command.equalsIgnoreCase("time")) // get the RTC time on device
    {
        printDateTime();
    }
    else if (command.equalsIgnoreCase("reset"))
    {
        autosampler.saveConfig();
        hardwareReset();
    }
    else if (command.equalsIgnoreCase("bootsel"))
    {
        Serial.println("INFO: Entering BOOTSEL mode...");
        sleep_ms(1000);
        rom_reset_usb_boot(LED_PIN, 0);
    }
    else if (command.equalsIgnoreCase("blink_en"))
    {
        blinkLED = true;
        Serial.println("INFO: LED blinking enabled.");
    }
    else if (command.equalsIgnoreCase("blink_dis"))
    {
        blinkLED = false;
        digitalWrite(LED_PIN, HIGH);
        Serial.println("INFO: LED blinking disabled.");
    }
    else if (command.equalsIgnoreCase("set_name"))
    {
        if (valueCount == 2)
        {
            String newName = values[1];
            if (autosampler.setName(newName))
            {
                Serial.println("INFO: Name set to: " + newName);
            }
        }
        else
        {
            Serial.println("ERROR: Invalid command format, expected format is setName:<name>");
        }
    }
    else if (command.equalsIgnoreCase("get_name"))
    {
        Serial.println("Name: " + autosampler.getName());
    }
    else if (command.equalsIgnoreCase("setPin"))
    {
        if (valueCount == 4)
        {
            int pulsePin = values[1].toInt();
            int directionPin = values[2].toInt();
            int enablePin = values[3].toInt();
            autosampler.setPin(pulsePin, directionPin, enablePin);
            Serial.println("INFO: Pins set to: Pulse=" + String(pulsePin) + ", Direction=" + String(directionPin) + ", Enable=" + String(enablePin));
        }
        else
        {
            Serial.println("ERROR: Invalid command format, expected format is setPin:<pulsePin>:<directionPin>:<enablePin>");
        }
    }
    else if (command.equalsIgnoreCase("readEncoder"))
    {
        autosampler.readEncoder();
    }
    else if (command.equalsIgnoreCase("setPosition"))
    {
        if (valueCount == 2)
        {
            int position = values[1].toInt();
            // check if position is a int using C++ method
            if (position == 0 && values[1] != "0")
            {
                Serial.println("ERROR: Invalid position value, expected an integer.");
            }
            autosampler.setCurrentPosition(position);
            Serial.println("SUCCESS: Position set to: " + String(autosampler.getCurrentPosition()));
        }
        else
        {
            Serial.println("ERROR: Invalid command format, expected format is setPosition:<position>");
        }
    }
    else if (command.equalsIgnoreCase("getPosition"))
    {
        Serial.println("INFO: Current position: " + String(autosampler.getCurrentPosition()));
    }
    else if (command.equalsIgnoreCase("setDirection"))
    {
        if (valueCount == 2)
        {
            bool direction = (values[1] == "1" || values[1].equalsIgnoreCase("left"));
            autosampler.setCurrentDirection(direction);
            Serial.println("INFO: Direction set to: " + String(autosampler.getCurrentDirection()));
        }
        else
        {
            Serial.println("ERROR: Invalid command format, expected format is setDirection:<direction>");
        }
    }
    else if (command.equalsIgnoreCase("getDirection"))
    {
        Serial.println("INFO: Current direction: " + autosampler.getCurrentDirection());
    }
    else if (command.equalsIgnoreCase("getFailSafePosition"))
    {
        Serial.println("INFO: Fail safe position: " + String(autosampler.getFailSafePosition()));
    }
    else if (command.equalsIgnoreCase("setFailSafePosition"))
    {
        if (valueCount == 2)
        {
            int failSafePosition = values[1].toInt();
            autosampler.setFailSafePosition(failSafePosition);
            Serial.println("INFO: Fail safe position set to: " + String(autosampler.getFailSafePosition()));
        }
        else
        {
            Serial.println("ERROR: Invalid command format, expected format is setFailSafePosition:<position>");
        }
    }
    else if (command.equalsIgnoreCase("moveToSlot"))
    {
        if (valueCount == 2)
        {
            String slot = values[1];
            autosampler.moveToSlot(slot);
        }
        else
        {
            Serial.println("ERROR: Invalid command format, expected format is moveToSlot:<slot>");
        }
    }
    else if (command.equalsIgnoreCase("setSlotPosition"))
    {
        if (valueCount == 3)
        {
            String slot = values[1];
            int position = values[2].toInt();
            autosampler.setSlotPosition(slot, position);
        }
        else
        {
            Serial.println("ERROR: Invalid command format, expected format is setSlotPosition:<slot>:<position>");
        }
    }
    else if (command.equalsIgnoreCase("deleteSlot"))
    {
        if (valueCount == 2)
        {
            String slot = values[1];
            autosampler.deleteSlot(slot);
        }
        else
        {
            Serial.println("ERROR: Invalid command format, expected format is deleteSlot:<slot>");
        }
    }
    else if (command.equalsIgnoreCase("setRatio"))
    {
        if (valueCount == 2)
        {
            ratio = values[1].toFloat();
            if (ratio <= 0)
            {
                Serial.println("ERROR: Invalid ratio value, must be greater than 0.");
                ratio = 1.0; // reset to default
            }
            Serial.println("INFO: Ratio set to: " + String(ratio));
        }
        else
        {
            Serial.println("ERROR: Invalid command format, expected format is setRatio:<value>");
        }
    }
    else if (command.equalsIgnoreCase("getRatio"))
    {
        Serial.println("INFO: Current ratio: " + String(ratio));
    }
    else if (command.equalsIgnoreCase("generateRampProfile"))
    {
        generateRampProfile();
    }
    else if (command.equalsIgnoreCase("setRampSteepness"))
    {
        if (valueCount == 2)
        {
            ramp_curve_scale = values[1].toFloat();
            if (ramp_curve_scale <= 0)
            {
                Serial.println("ERROR: Invalid steepness value, must be greater than 0.");
            }
            generateRampProfile(); // regenerate the ramp profile
            Serial.println("INFO: Ramp steepness set to: " + String(ramp_curve_scale));
        }
        else
        {
            Serial.println("ERROR: Invalid command format, expected format is setRampSteepness:<value>");
        }
    }
    else if (command.equalsIgnoreCase("setRampMinInterval"))
    {
        if (valueCount == 2)
        {
            ramp_min_interval = values[1].toInt();
            if (ramp_min_interval <= 0)
            {
                Serial.println("ERROR: Invalid minimum interval value, must be greater than 0.");
            }
            generateRampProfile(); // regenerate the ramp profile
            Serial.println("INFO: Ramp minimum interval set to: " + String(ramp_min_interval));
        }
        else
        {
            Serial.println("ERROR: Invalid command format, expected format is setRampMinInterval:<value>");
        }
    }
    else if (command.equalsIgnoreCase("setRampMaxInterval"))
    {
        if (valueCount == 2)
        {
            ramp_max_interval = values[1].toInt();
            if (ramp_max_interval <= 0)
            {
                Serial.println("ERROR: Invalid maximum interval value, must be greater than 0.");
            }
            generateRampProfile(); // regenerate the ramp profile
            Serial.println("INFO: Ramp maximum interval set to: " + String(ramp_max_interval));
        }
        else
        {
            Serial.println("ERROR: Invalid command format, expected format is setRampMaxInterval:<value>");
        }
    }
    else if (command.equalsIgnoreCase("dumpSlotsConfig"))
    {
        autosampler.dumpSlotsConfig();
    }
    else if (command.equalsIgnoreCase("dumpGlobalConfig"))
    {
        autosampler.dumpGlobalConfig();
    }
    else if (command.equalsIgnoreCase("moveToLeftMost"))
    {
        autosampler.moveToLeftMost();
    }
    else if (command.equalsIgnoreCase("moveToRightMost"))
    {
        autosampler.moveToRightMost();
    }
    else if (command.equalsIgnoreCase("debug"))
    {
        DEBUG = !DEBUG;
        autosampler.saveConfig();
        Serial.println("INFO: Debug mode " + String(DEBUG ? "enabled" : "disabled"));
    }
    else if (command.equalsIgnoreCase("holding"))
    {
        HOLDING = !HOLDING;
        autosampler.assertHolding();
        autosampler.saveConfig();
        Serial.println("INFO: Holding mode " + String(HOLDING ? "enabled" : "disabled"));
    }
    else if (command.equalsIgnoreCase("queryHolding"))
    {
        Serial.println("INFO: Holding " + String(HOLDING ? "enabled" : "disabled"));
    }
    else if (command.equalsIgnoreCase("queryDebug"))
    {
        Serial.println("INFO: Debug " + String(DEBUG ? "enabled" : "disabled"));
    }
    else
    {
        Serial.println("ERROR: Unknown command, type 'help' for a list of commands.");
    }
}

void setup()
{
    delay(1000);
    inputString.reserve(MAX_BUFFER_SIZE); // reserve memory for input
    Serial.begin(BAUD_RATE);
    while (!Serial)
        ; // Wait until the serial connection is open

    delay(1000);
    LittleFSConfig cfg;
    cfg.setAutoFormat(true);
    LittleFS.setConfig(cfg);
    if (!LittleFS.begin())
    {
        Serial.printf("ERROR: Unable to start LittleFS. Did you select a filesystem size in the menus?, Exiting...\n");
        return;
    }
    autosampler.begin();   // Initialize the autosampler
    generateRampProfile(); // Initialize the ramp profile

    rtc_init();
    datetime_t t = autosampler.getDateTime();
    rtc_set_datetime(&t);

    pinMode(LED_PIN, OUTPUT); // Set the LED pin as output
    digitalWrite(LED_PIN, HIGH);

    Wire1.setSDA(ENCODER_SDA_PIN); // Set the SDA pin for the encoder
    Wire1.setSCL(ENCODER_SCL_PIN); // Set the SCL pin for the encoder
    // init the direction pin for the encoder
    pinMode(ENCODER_DIR_PIN, OUTPUT);
    digitalWrite(ENCODER_DIR_PIN, LOW); // Set the direction pin to LOW
    // init the PGO pin for the encoder
    pinMode(ENCODER_PGO_PIN, OUTPUT);
    digitalWrite(ENCODER_PGO_PIN, HIGH); // Set the PGO pin to HIGH
    // init the encoder
    Wire1.begin();
    // autosampler.readEncoder();
}

void generateRampProfile()
{
    // fill the ramp profile array
    for (int i = 0; i < RAMP_SIZE; ++i)
    {
        float x = (ramp_curve_scale * i) / (RAMP_SIZE - 1); // x in [0, ramp_curve_scale]
        float tanh_val = tanhf(x);                          // range [0, ~1)
        float ramp_val = ramp_min_interval + (1.0f - tanh_val) * (ramp_max_interval - ramp_min_interval);
        rampProfile[i] = (int)(ramp_val + 0.5f); // round to nearest int
    }

    // debug output
    if (DEBUG)
    {
        Serial.printf("DEBUG: Ramp profile generated with min interval %d, max interval %d, curve scale %.2f\n", ramp_min_interval, ramp_max_interval, ramp_curve_scale);
        Serial.println("DEBUG: Ramp profile initialized:");
        for (int i = 0; i < RAMP_SIZE; ++i)
        {
            Serial.printf("%d ", rampProfile[i]);
        }
        Serial.println();
    }
}

void loop()
{
    autosampler.updateMovement();
    autosampler.blinkLEDTask();
    if (stringComplete)
    {
        parseInputString();
        stringComplete = false;
        inputString = ""; // clear the input string
    }
}

void serialEvent()
{
    while (Serial.available())
    {
        if (!blinkLED)
        {
            digitalWrite(LED_PIN, LOW);
        }
        char inChar = (char)Serial.read();
        inputString += inChar;

        if (inChar == '\n')
        {
            stringComplete = true;
            if (!blinkLED)
            {
                digitalWrite(LED_PIN, HIGH);
            }
            return;
        }
        else if (inputString.length() >= MAX_BUFFER_SIZE)
        {
            Serial.println("ERROR: Input command too long.");
            inputString = "";
        }
        if (!blinkLED)
        {
            digitalWrite(LED_PIN, HIGH);
        }
    }
}