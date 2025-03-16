#include <VFS.h>
#include <LittleFS.h>

const bool DEBUG = true; // Set to true to enable debug messages

String inputString = ""; // a string to hold incoming data
float version = 0.01;    // version of the code

const int MAX_POSITION = 16000;               // Maximum position of the stepper motor
const int TIME_INTERVAL_BETWEEN_STEPS_MS = 3; // Time interval between steps in microseconds
const int PULSE_PIN = 7;
const int DIRECTION_PIN = 16;
const int ENABLE_PIN = 18;
const char STANDARD_DELIMITER = ':';
const int MAX_BUFFER_SIZE = 300;    // Maximum buffer size for input string
const int BAUD_RATE = 115200;       // Baud rate for serial communication
const pin_size_t led = LED_BUILTIN; // LED pin for debugging

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
    volatile int stepsRemaining = 0;

    unsigned long lastStepTime = 0;
    unsigned long moveStartTime = 0;

    void stopMovementWrapUp()
    {
        if (moveInProgress)
        {
            moveInProgress = false;
            stepsRemaining = 0;
            stopRequested = false;
            saveConfiguration();
            enableStepper(false);
            if (DEBUG)
            {
                int timeTaken = (millis() - moveStartTime) / 1000;
                Serial.printf("Info: Movement stopped, total time taken: %d seconds, currentPosition=%d\n", timeTaken, currentPosition);
            }
        }
    }

public:
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
                Serial.printf("Info: Configuration file content: %s\n", content.c_str());
                Serial.printf("Info: Configuration loaded, currentPosition=%d, currentDirection=%d, direction=%s\n", currentPosition, (int)currentDirection, direction);
            }
        }
        else
        {
            saveConfiguration(true);
        }
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

    void enableStepper(bool enable)
    {
        digitalWrite(enablePin, enable ? LOW : HIGH); // LOW enables driver
        isPoweredOn = enable;
    }
    void moveToPosition(int position)
    {
        position = constrain(position, 0, MAX_POSITION);
        int steps = position - currentPosition;
        if (DEBUG)
        {
            Serial.printf("Info: moveToPosition called with position=%d, steps=%d\n", position, steps);
        }
        if (steps != 0)
        {
            startMove(steps);
        }
    }
    void startMove(int steps)
    {
        if (steps == 0 || moveInProgress)
            return;

        moveStartTime = millis();
        currentDirection = (steps > 0);
        digitalWrite(directionPin, currentDirection ? HIGH : LOW);

        stepsRemaining = abs(steps);
        moveInProgress = true;
        stopRequested = false;

        enableStepper(true);
        lastStepTime = millis();
    }
    void updateMovement()
    {
        if (!moveInProgress)
            return;
        if (stopRequested)
        {
            Serial.println("Info: Movement interrupted by user");
            stopMovementWrapUp();
            return;
        }
        unsigned long currentTime = millis();
        if (currentTime - lastStepTime >= TIME_INTERVAL_BETWEEN_STEPS_MS)
        {
            digitalWrite(pulsePin, HIGH);
            delayMicroseconds(1);
            digitalWrite(pulsePin, LOW);

            stepsRemaining--;
            currentPosition += currentDirection ? 1 : -1;
            lastStepTime = currentTime;

            if (DEBUG)
            {
                Serial.printf("Info: One step taken, currentPosition=%d, stepsRemaining=%d\n", currentPosition, stepsRemaining);
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
};

Autosampler autosampler(PULSE_PIN, DIRECTION_PIN, ENABLE_PIN);

void setup()
{
    delay(3000);
    pinMode(led, OUTPUT); // Set the LED pin as output
    digitalWrite(led, HIGH);
    LittleFSConfig cfg;
    cfg.setAutoFormat(true);
    LittleFS.setConfig(cfg);
    if (!LittleFS.begin())
    {
        Serial.printf("ERROR: Unable to start LittleFS. Did you select a filesystem size in the menus?\n");
        return;
    }
    VFS.root(LittleFS); // Mount the filesystem

    Serial.begin(BAUD_RATE);
    while (!Serial)
        ;                                 // Wait until the serial connection is open
    inputString.reserve(MAX_BUFFER_SIZE); // reserve memory for input
    autosampler.begin();                  // Initialize the autosampler
}

void loop()
{
    autosampler.updateMovement();

    while (Serial.available() > 0)
    {
        digitalWrite(led, LOW);
        char inChar = (char)Serial.read();
        inputString += inChar;

        if (inChar == '\n')
        {
            parseInputString();
        }
        else if (inputString.length() >= MAX_BUFFER_SIZE)
        {
            Serial.println("Error: Input command too long.");
            inputString = "";
        }
        digitalWrite(led, HIGH);
    }
}

// parse the input string, the format is <id>:<command>:<value1>:<value2>...
void parseInputString()
{
    // trim
    inputString.trim();
    if (inputString.length() == 0)
    {
        Serial.println("Error: Empty command.");
        return;
    }

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
    if (valueCount < 2)
    {
        Serial.println("Error: Invalid command format, expected format is <id>:<command>:<value1>:<value2>...");
        return;
    }

    // debug, print the values back
    Serial.print("Parsed values: [");
    for (int i = 0; i < valueCount; i++)
    {
        Serial.print(values[i]);
        if (i < valueCount - 1)
            Serial.print(", ");
    }
    Serial.println("]");

    int id = values[0].toInt();
    String command = values[1];

    if (command == "help")
    {
        Serial.println("Info: Autosampler control commands:");
        Serial.println("  <id>:help - Show this help message.");
        Serial.println("  <id>:ping - Check the connection to the autosampler.");
        Serial.println("  <id>:setPosition:<position> - Set the current position of the autosampler.");
        Serial.println("  <id>:getPosition - Get the current position of the autosampler.");
        Serial.println("  <id>:setDirection:<direction> - Set the direction of the autosampler (1 for left, 0 for right).");
        Serial.println("  <id>:getDirection - Get the current direction of the autosampler.");
        Serial.println("  <id>:getFailSafePosition - Get the fail safe position of the autosampler.");
        Serial.println("  <id>:setFailSafePosition:<position> - Set the fail safe position of the autosampler.");
        Serial.println("  <id>:moveTo:<position> - Move to a specific position.");
    }
    else if (command == "ping")
    {
        Serial.println("Ping: Pico Autosampler Control Version " + String(version));
    }
    else if (command == "setPosition")
    {
        if (valueCount == 3)
        {
            int position = values[2].toInt();
            // check if position is a int using C++ method
            if (position == 0 && values[2] != "0")
            {
                Serial.println("Error: Invalid position value, expected an integer.");
            }
            autosampler.setCurrentPosition(position);
            Serial.println("Info: Position set to: " + String(autosampler.getCurrentPosition()));
        }
        else
        {
            Serial.println("Error: Invalid command format, expected format is <id>:setPosition:<position>");
        }
    }
    else if (command == "getPosition")
    {
        Serial.println("Info: Current position: " + String(autosampler.getCurrentPosition()));
    }
    else if (command == "setDirection")
    {
        if (valueCount == 3)
        {
            bool direction = (values[2] == "1" || values[2].equalsIgnoreCase("left"));
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
            Serial.println("Error: Invalid command format, expected format is <id>:setDirection:<direction>");
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
        if (valueCount == 3)
        {
            int failSafePosition = values[2].toInt();
            autosampler.setFailSafePosition(failSafePosition);
            Serial.println("Info: Fail safe position set to: " + String(autosampler.getFailSafePosition()));
        }
        else
        {
            Serial.println("Error: Invalid command format, expected format is <id>:setFailSafePosition:<position>");
        }
    }
    else if (command == "moveTo")
    {
        if (valueCount == 3)
        {
            int targetPosition = values[2].toInt();
            // check if position is a int using C++ method
            if (targetPosition == 0 && values[2] != "0")
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
            Serial.println("Error: Invalid command format, expected format is <id>:moveTo:<position>");
        }
    }
    else if (command == "stop")
    {
        autosampler.stopMovement();
        Serial.println("Info: Movement stopped.");
    }
    else
    {
        Serial.println("Error: Unknown command, type '0:help' for a list of commands.");
    }

    // clear the input string
    inputString = "";
}