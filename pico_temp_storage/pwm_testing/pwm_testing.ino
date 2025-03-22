#include <Arduino.h>
#include "hardwarePWM.h" // The header with setHardwarePWM_Frac()

// Pins
static const uint PWM_OUT_PIN = 20;  // Pin generating the PWM
static const uint PWM_MEAS_PIN = 22; // Pin counting pulses (jumper from 20 -> 22)

// Initial frequency and duty
static float freq = 50000.f; // 50 kHz
static float duty = 50.f;    // 50%

// We'll store a pulse counter in a volatile long
volatile long g_pulseCount = 0;

// ISR increments on rising edges
void measurePulseISR()
{
    g_pulseCount++;
}

// We'll measure pulses over 3 seconds
static const unsigned long MEASURE_INTERVAL_MS = 3000;
static unsigned long lastMeasureMs = 0;

void setup()
{
    Serial.begin(115200);
    while (!Serial)
    {
        delay(10);
    }
    Serial.println("=== PWM with on-the-fly freq/duty, 3s sampling ===");

    // Configure measuring pin
    pinMode(PWM_MEAS_PIN, INPUT);
    attachInterrupt(digitalPinToInterrupt(PWM_MEAS_PIN), measurePulseISR, RISING);

    // Set initial PWM on PWM_OUT_PIN
    bool ok = setHardwarePWM_Frac(PWM_OUT_PIN, freq, duty);
    if (!ok)
    {
        Serial.printf("Failed to set PWM on pin %u with freq=%d Hz, duty=%d%%\n",
                      PWM_OUT_PIN, freq, duty);
        while (true)
        {
            delay(1000);
        }
    }
    Serial.printf("PWM set on pin %u => freq=%d Hz, duty=%d%%\n",
                  PWM_OUT_PIN, freq, duty);

    Serial.println("\nEnter e.g. '20000 75' or '15000' to change freq/duty:\n"
                   " - Two numbers => freq (Hz), duty (%%)\n"
                   " - One number => freq only, keep duty\n");
}

void loop()
{
    // 1) Every 3 seconds, measure pulses => frequency
    unsigned long now = millis();
    if (now - lastMeasureMs >= MEASURE_INTERVAL_MS)
    {
        lastMeasureMs = now;
        long pulses = g_pulseCount;
        g_pulseCount = 0; // reset

        // The frequency is pulses / 3.0 seconds
        float freqMeasured = (float)pulses / (MEASURE_INTERVAL_MS / 1000.0f);
        Serial.printf("Measured %ld pulses in %u ms => ~%.1f Hz\n",
                      pulses, MEASURE_INTERVAL_MS, freqMeasured);
    }

    // 2) Check for user input to update freq/duty on the fly
    if (Serial.available() > 0)
    {
        // read a line
        String line = Serial.readStringUntil('\n');
        line.trim();
        if (line.length() == 0)
            return;

        int spaceIndex = line.indexOf(' ');
        if (spaceIndex < 0)
        {
            // single integer => freq only
            float newFreq = line.toFloat();
            if (newFreq <= 0)
            {
                Serial.println("Error: freq must be > 0");
                return;
            }
            freq = newFreq;
        }
        else
        {
            // freq + duty
            String freqStr = line.substring(0, spaceIndex);
            String dutyStr = line.substring(spaceIndex + 1);
            float newFreq = freqStr.toFloat();
            float newDuty = dutyStr.toFloat();
            if (newFreq <= 0 || newDuty < 0 || newDuty > 100)
            {
                Serial.println("Error: freq>0, duty in [0..100]. e.g. '30000 60'");
                return;
            }
            freq = newFreq;
            duty = newDuty;
        }

        // set the new freq/duty
        bool ok = setHardwarePWM_Frac(PWM_OUT_PIN, freq, duty);
        if (!ok)
        {
            Serial.printf("Failed to set freq=%f, duty=%f%% (out of range?), reverting.\n", freq, duty);
        }
        else
        {
            Serial.printf("Updated PWM => freq=%f Hz, duty=%f%%\n", freq, duty);
        }
    }
}
