#pragma once

#ifndef HELPERS_H
#define HELPERS_H

#include <stdio.h>
#include "pico/stdlib.h"
#include "hardware/rtc.h"
#include "hardware/resets.h"
#include "hardware/watchdog.h"

#include "pico/util/datetime.h"

uint64_t getCurrentTime();
void printDateTime();
void setDateTime(int year, int month, int day, int dotw, int hour, int minute, int second);
void hardwareReset();

#endif