#!/usr/bin/python

import time

standard_actiview_trigger_codes = dict(
    START_LISTENING = 255,
    STOP_LISTENING = 256,
    RESET_PINS = 0)
trigger_code_delay = .05 # Seconds

inpout32_addr = 888

wait = time.sleep

if inpout32_addr is not None:
    from ctypes import windll
    send = lambda x: windll.inpout32.Out32(inpout32_addr, x)
else:
    from psychopy.parallel import setData
    send = setData

def trigger(trigger_code):
    print "Sending", trigger_code
    send(trigger_code)
    wait(trigger_code_delay)
    print "Sending", standard_actiview_trigger_codes['RESET_PINS']
    send(standard_actiview_trigger_codes['RESET_PINS'])
    wait(trigger_code_delay)

trigger(standard_actiview_trigger_codes['START_LISTENING'])

for x in range(10):
    trigger(x + 1)
    wait(2)

trigger(standard_actiview_trigger_codes['STOP_LISTENING'])

print "Done"
