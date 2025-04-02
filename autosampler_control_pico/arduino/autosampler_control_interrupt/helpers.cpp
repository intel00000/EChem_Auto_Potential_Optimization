#include <Arduino.h>
#include "helpers.h"

void getCurrentTime()
{
    uint64_t us = to_us_since_boot(get_absolute_time());
    time_t seconds = us / 1000000;
    Serial.printf("INFO: Current time since boot: %llu us, %ld s\n", us, seconds);
}

void printDateTime()
{
    datetime_t datetime;
    rtc_get_datetime(&datetime);
    Serial.printf("INFO: RTC Time: %d-%02d-%02d %02d:%02d:%02d\n", datetime.year, datetime.month, datetime.day, datetime.hour, datetime.min, datetime.sec);
}

void setDateTime(int year, int month, int day, int hour, int minute, int second)
{
    datetime_t datetime;
    datetime.year = year;
    datetime.month = month;
    datetime.day = day;
    datetime.hour = hour;
    datetime.min = minute;
    datetime.sec = second;
    rtc_set_datetime(&datetime);
    Serial.println("SUCCESS: RTC time set.");
}

void hardwareReset()
{
    Serial.println("SUCCESS: Resetting the device.");
    // use watchdog to reset the device
    watchdog_enable(1, true);
    while (1)
        ;
}