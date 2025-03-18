#include <VFS.h>
#include <Ticker.h>
#include <LittleFS.h>
#include <ArduinoJson.h>

#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/time.h"

#include "helpers.h"

#define LED_PIN LED_BUILTIN

const bool DEBUG = true; // Set to true to enable debug messages

String inputString = "";              // a string to hold incoming data
volatile bool stringComplete = false; // whether the string is complete

const float version = 0.01;     // version of the code
const int MAX_POSITION = 16000; // Maximum position of the stepper motor

const int PULSE_PIN = 12;
const int DIRECTION_PIN = 14;
const int ENABLE_PIN = 15;

const char STANDARD_DELIMITER = ':';
const int MAX_BUFFER_SIZE = 300; // Maximum buffer size for input string
const int BAUD_RATE = 115200;    // Baud rate for serial communication

// Ramp profile in microseconds
const int rampProfile[] = {
    10'000, 10'000, 10'000, 10'000, 10'000,
    9'000, 9'000, 9'000, 9'000, 8'000, 8'000, 8'000, 8'000, 7'000, 7'000, 7'000, 7'000, 6'000, 6'000, 6'000, 6'000,
    5'000, 5'000, 5'000, 4'000, 4'000, 4'000, 3'000, 3'000, 3'000, 2'000, 2'000};
;
const int rampProfileLength = sizeof(rampProfile) / sizeof(rampProfile[0]);

class Autosampler
{
private:
    uint8_t pulsePin;
    uint8_t directionPin;
    uint8_t enablePin;

    bool isPoweredOn;
    int currentPosition;
    int failSafePosition;
    bool currentDirection; // true: left, false: right

    volatile bool moveInProgress = false;
    volatile bool stopRequested = false;
    volatile int stepsTaken = 0;
    volatile int stepsRemaining = 0;
    unsigned long moveStartTime = 0;

    JsonDocument slotsConfig; // JSON object to store slot positions
    alarm_pool_t *pool;
    alarm_id_t moveAlarmId = -1; // Store alarm ID

    static int64_t updateMovementCallback(alarm_id_t id, void *user_data)
    {
        Autosampler *self = static_cast<Autosampler *>(user_data); // Cast void pointer to Autosampler pointer
        self->updateMovement();
        return 0;
    }
    void stopMovementWrapUp()
    {
        if (moveInProgress)
        {
            moveInProgress = false;
            stepsTaken = 0;
            stepsRemaining = 0;
            stopRequested = false;
            saveConfiguration();
            enableStepper(false);
            // Schedule a delayed update to check for further movement
            // moveAlarmId = add_alarm_in_ms(rampProfile[0], updateMovementCallback, this, false);
            moveAlarmId = alarm_pool_add_alarm_in_us(pool, rampProfile[0], updateMovementCallback, this, false);
            if (DEBUG)
            {
                double timeTaken = (micros() - moveStartTime) / 1e6;
                Serial.printf("DEBUG: Movement stopped, total time taken: %fs, currentPosition=%d\n", timeTaken, currentPosition);
            }
        }
    }
    void enableStepper(bool enable)
    {
        digitalWrite(enablePin, enable ? LOW : HIGH); // LOW enables driver
        isPoweredOn = enable;
    }
    unsigned int getStepInterval()
    {
        unsigned int interval;

        if (stepsTaken < rampProfileLength)
        {
            // Ramp-up phase
            interval = rampProfile[stepsTaken];
        }
        else if (stepsRemaining <= rampProfileLength)
        {
            // Ramp-down phase
            interval = rampProfile[stepsRemaining - 1];
        }
        else
        {
            // Constant (steady) speed
            interval = rampProfile[rampProfileLength - 1];
        }

        return interval;
    }
    void saveConfiguration(bool initialValues = false)
    {
        // Save the current position and direction to the configuration file
        File configFile = LittleFS.open("/autosampler_config.txt", "w");
        if (configFile)
        {
            if (initialValues)
            {
                currentPosition = 0;
                currentDirection = true;
            }
            configFile.printf("%d,%d,%s\n", currentPosition, currentDirection, currentDirection ? "Left" : "Right");
            configFile.close();
            Serial.println("Info: Configuration saved.");
        }
        else
        {
            Serial.println("Error: Unable to save configuration file.");
        }
    }
    void loadConfiguration()
    {
        // attempt to read the configuration from LittleFS
        // the format is "currentPosition, currentDirection(either 1/0), currentDirection(either Left/Right)"
        File configFile = LittleFS.open("/autosampler_config.txt", "r");
        if (configFile)
        {
            String content = configFile.readStringUntil('\n');
            configFile.close();

            char direction[10];
            int currentDirectionTemp;
            if (sscanf(content.c_str(), "%d,%d,%s", &currentPosition, &currentDirectionTemp, direction) != 3)
            {
                Serial.println("Error: Unable to parse configuration file.");
                saveConfiguration(true);
            }
            currentDirection = (currentDirectionTemp == 1); // 1 for left, 0 for right
            if (DEBUG)
            {
                Serial.printf("DEBUG: Configuration file content: %s\n", content.c_str());
                Serial.printf("DEBUG: Configuration loaded, currentPosition=%d, currentDirection=%d, direction=%s\n", currentPosition, (int)currentDirection, direction);
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
            Serial.println("Error: Unable to open slots configuration file.");
            return;
        }
        if (initialValues)
        {
            Serial.println("Info: initializing slots configuration.");
            // save a default configuration
            slotsConfig.clear();
            slotsConfig["waste"] = 0;
            slotsConfig["fail-safe"] = 0;
            slotsConfig["0"] = 0;
            // save the default configuration
            serializeJsonPretty(slotsConfig, file);
            file.close();
        }
        else
        {
            serializeJsonPretty(slotsConfig, file);
            file.close();
            Serial.println("Info: Slots configuration saved.");
        }
    }
    void loadSlotsConfig()
    {
        File file = LittleFS.open("/slots_config.json", "r");
        if (file)
        {
            DeserializationError error = deserializeJson(slotsConfig, file);
            file.close();
            if (error)
            {
                saveSlotsConfig(true);
            }
            else
            {
                Serial.println("Info: Slots configuration loaded.");
            }
        }
        else
        {
            saveSlotsConfig(true);
        }
    }

public:
    Ticker updateMovementTicker; // Ticker to update the movement

    Autosampler(uint8_t pulse, uint8_t direction, uint8_t enable)
        : pulsePin(pulse),
          directionPin(direction),
          enablePin(enable),
          isPoweredOn(false),
          currentPosition(-1),
          failSafePosition(0),
          currentDirection(true) {}

    void begin()
    {
        pinMode(pulsePin, OUTPUT);
        pinMode(directionPin, OUTPUT);
        pinMode(enablePin, OUTPUT);
        digitalWrite(pulsePin, LOW);
        digitalWrite(directionPin, LOW);
        digitalWrite(enablePin, HIGH); // disable motor initially

        pool = alarm_pool_create_with_unused_hardware_alarm(1); // create an alarm pool
        loadConfiguration();
        loadSlotsConfig();
    }

    void moveToPosition(int position)
    {
        if (moveInProgress)
        {
            Serial.println("Error: Movement already in progress, you should stop the current movement first.");
            return;
        }
        position = constrain(position, 0, MAX_POSITION);
        int steps = position - currentPosition;
        if (DEBUG)
        {
            Serial.printf("DEBUG: moveToPosition called with position=%d, steps=%d\n", position, steps);
        }
        if (steps == 0)
        {
            Serial.println("Success: Already at the target position.");
            return;
        }

        currentDirection = (steps > 0);
        digitalWrite(directionPin, currentDirection ? HIGH : LOW);

        moveInProgress = true;
        stopRequested = false;
        stepsTaken = 0;
        stepsRemaining = abs(steps);
        moveStartTime = micros();

        enableStepper(true);
    }
    void updateMovement()
    {
        if (!moveInProgress)
        {
            // moveAlarmId = add_alarm_in_ms(rampProfile[0], updateMovementCallback, this, false);
            moveAlarmId = alarm_pool_add_alarm_in_us(pool, rampProfile[0], updateMovementCallback, this, false);
            return;
        }
        if (stopRequested)
        {
            stopMovementWrapUp();
            Serial.println("Info: Movement interrupted by user");
            return;
        }
        unsigned long interval = getStepInterval();
        digitalWrite(pulsePin, HIGH);
        delayMicroseconds((unsigned int)interval);
        digitalWrite(pulsePin, LOW);
        stepsRemaining--;
        stepsTaken++;
        currentPosition += currentDirection ? 1 : -1;

        if (DEBUG)
        {
            getCurrentTime();
            Serial.printf("DEBUG: One step taken, stepsTaken=%d, stepsRemaining=%d, currentPosition=%d, interval=%luμs\n", stepsTaken, stepsRemaining, currentPosition, interval);
        }
        if (stepsRemaining <= 0)
        {
            stopMovementWrapUp();
            return;
        }
        // moveAlarmId = add_alarm_in_ms(interval, updateMovementCallback, this, false);
        moveAlarmId = alarm_pool_add_alarm_in_us(pool, interval, updateMovementCallback, this, false);
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
        currentPosition = constrain(position, 0, MAX_POSITION);
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
        failSafePosition = constrain(position, 0, MAX_POSITION);
        saveConfiguration();
    }
    void moveToSlot(String slot)
    {
        if (!slotsConfig[slot].is<JsonVariant>())
        {
            Serial.printf("Error: Slot %s not found.\n", slot);
            return;
        }
        int targetPosition = slotsConfig[slot].as<int>();
        Serial.printf("Info: Moving to slot %s\n", slot);
        moveToPosition(targetPosition);
    }
    void setSlotPosition(String slot, int position)
    {
        if (slotsConfig[slot].is<JsonVariant>())
        {
            Serial.printf("Success: Slot %s position updated to %d\n", slot, position);
        }
        else
        {
            Serial.printf("Success: Slot %s position set to %d\n", slot, position);
        }
        slotsConfig[slot] = constrain(position, 0, MAX_POSITION);
        saveSlotsConfig();
    }
    void deleteSlotPosition(String slot)
    {
        if (!slotsConfig[slot].is<JsonVariant>())
        {
            Serial.printf("Error: Slot %s not found.\n", slot);
            return;
        }
        slotsConfig.remove(slot);
        saveSlotsConfig();
        Serial.printf("Success: Slot %s deleted.\n", slot);
    }
    void dumpSlotsConfig()
    {
        Serial.print("Info: Slots configuration: ");
        serializeJson(slotsConfig, Serial);
        Serial.println();
    }
};

Autosampler autosampler(PULSE_PIN, DIRECTION_PIN, ENABLE_PIN);

// parse the input string, the format is <command>:<value1>:<value2>...
void parseInputString()
{
    inputString.trim(); // trim
    if (inputString.length() == 0)
    {
        Serial.println("Error: Empty command.");
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
        Serial.println("Error: Invalid command format, expected format is <command>:<value1>:<value2>...");
        return;
    }

    String command = values[0];

    // print back the parsed values
    if (DEBUG)
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

    if (command == "help")
    {
        Serial.println("Info: Autosampler control commands:");
        Serial.println("    help - Show this help message.");
        Serial.println("    ping - Check the connection to the autosampler.");
        Serial.println("    setPosition:<position> - Set the current position of the autosampler.");
        Serial.println("    getPosition - Get the current position of the autosampler.");
        Serial.println("    setDirection:<direction> - Set the direction of the autosampler (1 for left, 0 for right).");
        Serial.println("    getDirection - Get the current direction of the autosampler.");
        Serial.println("    getFailSafePosition - Get the fail safe position of the autosampler.");
        Serial.println("    setFailSafePosition:<position> - Set the fail safe position of the autosampler.");
        Serial.println("    moveTo:<position> - Move to a specific position.");
        Serial.println("    stop - Stop the autosampler movement.");
        Serial.println("    moveToSlot:<slot> - Move to a specific slot.");
        Serial.println("    setSlotPosition:<slot>:<position> - Set the position of a slot.");
        Serial.println("    deleteSlotPosition:<slot> - Delete the position of a slot.");
        Serial.println("    dumpSlotsConfig - Dump the slots configuration.");
        Serial.println("    stime:<year>:<month>:<day>:<hour>:<minute>:<second> - Set the RTC time on the device.");
        Serial.println("    gtime - Get the RTC time on the device.");
        Serial.println("    reset - Reset the device.");
    }
    else if (command == "stop")
    {
        autosampler.stopMovement();
        Serial.println("Info: Movement stopped.");
    }
    else if (command == "moveTo")
    {
        if (valueCount == 2)
        {
            int targetPosition = values[1].toInt();
            // check if position is a int using C++ method
            if (targetPosition == 0 && values[1] != "0")
            {
                Serial.println("Error: Invalid target position value, expected an integer.");
            }
            else
            {
                autosampler.moveToPosition(targetPosition);
                Serial.println("Info: Moving to position " + String(autosampler.getCurrentPosition()));
            }
        }
        else
        {
            Serial.println("Error: Invalid command format, expected format is moveTo:<position>");
        }
    }
    else if (command == "ping")
    {
        Serial.println("Ping: Pico Autosampler Control Version " + String(version));
    }
    else if (command == "stime") // set the RTC time on device
    // format "0:stime:{now.year}:{now.month}:{now.day}:{now.hour}:{now.minute}:{now.second}"
    {
        if (valueCount == 7)
        {
            int year = values[1].toInt();
            int month = values[2].toInt();
            int day = values[3].toInt();
            int hour = values[4].toInt();
            int minute = values[5].toInt();
            int second = values[6].toInt();
            setDateTime(year, month, day, hour, minute, second);
        }
        else
        {
            Serial.println("Error: Invalid command format, expected format is stime:<year>:<month>:<day>:<hour>:<minute>:<second>");
        }
    }
    else if (command == "gtime") // get the RTC time on device
    {
        printDateTime();
    }
    else if (command == "reset")
    {
        hardwareReset();
    }
    else if (command == "setPosition")
    {
        if (valueCount == 2)
        {
            int position = values[1].toInt();
            // check if position is a int using C++ method
            if (position == 0 && values[1] != "0")
            {
                Serial.println("Error: Invalid position value, expected an integer.");
            }
            autosampler.setCurrentPosition(position);
            Serial.println("Info: Position set to: " + String(autosampler.getCurrentPosition()));
        }
        else
        {
            Serial.println("Error: Invalid command format, expected format is setPosition:<position>");
        }
    }
    else if (command == "getPosition")
    {
        Serial.println("Info: Current position: " + String(autosampler.getCurrentPosition()));
    }
    else if (command == "setDirection")
    {
        if (valueCount == 2)
        {
            bool direction = (values[1] == "1" || values[1].equalsIgnoreCase("left"));
            if (direction)
            {
                Serial.println("Info: Direction set to: Left");
            }
            else
            {
                Serial.println("Info: Direction set to: Right");
            }
            autosampler.setCurrentDirection(direction);
            Serial.println("Info: Direction set to: " + String(autosampler.getCurrentDirection()));
        }
        else
        {
            Serial.println("Error: Invalid command format, expected format is setDirection:<direction>");
        }
    }
    else if (command == "getDirection")
    {
        Serial.println("Info: Current direction: " + autosampler.getCurrentDirection());
    }
    else if (command == "getFailSafePosition")
    {
        Serial.println("Info: Fail safe position: " + String(autosampler.getFailSafePosition()));
    }
    else if (command == "setFailSafePosition")
    {
        if (valueCount == 2)
        {
            int failSafePosition = values[1].toInt();
            autosampler.setFailSafePosition(failSafePosition);
            Serial.println("Info: Fail safe position set to: " + String(autosampler.getFailSafePosition()));
        }
        else
        {
            Serial.println("Error: Invalid command format, expected format is setFailSafePosition:<position>");
        }
    }
    else if (command == "moveToSlot")
    {
        if (valueCount == 2)
        {
            autosampler.moveToSlot(values[1]);
        }
        else
        {
            Serial.println("Error: Invalid command format, expected format is moveToSlot:<slot>");
        }
    }
    else if (command == "setSlotPosition")
    {
        if (valueCount == 3)
        {
            int position = values[2].toInt();
            autosampler.setSlotPosition(values[1], position);
        }
        else
        {
            Serial.println("Error: Invalid command format, expected format is setSlotPosition:<slot>:<position>");
        }
    }
    else if (command == "deleteSlotPosition")
    {
        if (valueCount == 2)
        {
            autosampler.deleteSlotPosition(values[1]);
        }
        else
        {
            Serial.println("Error: Invalid command format, expected format is deleteSlotPosition:<slot>");
        }
    }
    else if (command == "dumpSlotsConfig")
    {
        autosampler.dumpSlotsConfig();
    }
    else
    {
        Serial.println("Error: Unknown command, type '0:help' for a list of commands.");
    }

    stringComplete = false;
    inputString = ""; // clear the input string
}

void setup()
{
    delay(1000);
    rtc_init();
    datetime_t t = {
        .year = 2020,
        .month = 06,
        .day = 05,
        .dotw = 5, // 0 is Sunday, so 5 is Friday
        .hour = 15,
        .min = 45,
        .sec = 00};
    rtc_set_datetime(&t);

    pinMode(LED_PIN, OUTPUT); // Set the LED pin as output
    digitalWrite(LED_PIN, HIGH);

    inputString.reserve(MAX_BUFFER_SIZE); // reserve memory for input
    Serial.begin(BAUD_RATE);
    while (!Serial)
        ; // Wait until the serial connection is open

    LittleFSConfig cfg;
    cfg.setAutoFormat(true);
    LittleFS.setConfig(cfg);
    if (!LittleFS.begin())
    {
        Serial.printf("ERROR: Unable to start LittleFS. Did you select a filesystem size in the menus?, Exiting...\n");
        return;
    }

    autosampler.begin(); // Initialize the autosampler
    autosampler.updateMovement();
}

void loop()
{
    if (stringComplete)
    {
        parseInputString();
    }
}

void serialEvent()
{
    while (Serial.available())
    {
        digitalWrite(LED_PIN, LOW);
        char inChar = (char)Serial.read();
        inputString += inChar;

        if (inChar == '\n')
        {
            stringComplete = true;
            digitalWrite(LED_PIN, HIGH);
            return;
        }
        else if (inputString.length() >= MAX_BUFFER_SIZE)
        {
            Serial.println("Error: Input command too long.");
            inputString = "";
        }
        digitalWrite(LED_PIN, HIGH);
    }
}