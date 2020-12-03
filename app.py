import numpy as np
import cv2
from PIL import Image, ImageTk
import keyboard
import pytesseract
import re
import pyWinhook
import threading
from time import sleep, perf_counter
import math

import tkinter as tk

import mss

digit_regex = r'\d+'

offset = 0.05 # km/h to go above (or below if negative) the speed limit
step = 2 # must match the "Cruise control grid step" setting


# 1080p
# current_speed_box = (1490, 710, 1525, 730)
# speed_limit_box = (1500, 780, 1525, 805)

# 1440p
current_speed_box = (1985, 945, 2050, 975)
speed_limit_box = (2000, 1040, 2033, 1075)

key_accel = 'w'
key_brake = 's'
key_cruise = 'c'
key_cruise_up = 'h'
key_cruise_dwn = 'n'

should_execute = False
running = True
current_speed = 0
speed_limit = 0
braking = False
accelerating = False
current_cruise = 0
minimum_cruise = 30 # km/h, minimum speed at which cruise can be enabled
maximum_cruise = 90 # km/h, maximum speed at which cruise can go up to


log_file = open('log.csv', 'w')
log_file.write('Speed, Limit, Cruise, Enabled, Accel, Brake\n')

# UI elements
dirty_ui = False
latest_speed_img = None
latest_limit_img = None

window = tk.Tk()
enabled_lbl = tk.Label(text=f'Enabled: {should_execute}')
cur_speed_lbl = tk.Label(text=f'Current: {current_speed}')
speed_limit_lbl = tk.Label(text=f'Limit: {speed_limit}')
cur_cruise_lbl = tk.Label(text=f'Cruise: {current_cruise}')
accel_lbl = tk.Label(text=f'Accelerating: {accelerating}')
braking_lbl = tk.Label(text=f'Braking: {braking}')
speed_img_lbl = tk.Label()
limit_img_lbl = tk.Label()
# /UI elements

def determine_commands(current, limit, cruise_active, cruise):
    accelerate = (current < minimum_cruise)
    brake = False #(current > (limit + 5))
    # print(f'Accel: {accelerate} Brake: {brake}')
    working_offset = offset if offset >= 1 else math.ceil(offset*limit) # either use the offset as-is, or if a fraction then use it as a % of the limit
    working_limit = min(limit + working_offset, maximum_cruise)
    increase_cruise = cruise_active and cruise < working_limit
    decrease_cruise = cruise_active and (cruise - step) >= working_limit
    activate_cruise = not cruise_active and current >= minimum_cruise
    return accelerate, brake, activate_cruise, increase_cruise, decrease_cruise


def execute_commands(accel, brake, enCruise, upCruise, dwnCruise):
    global current_cruise
    if accel: keyboard.press(key_accel)
    if brake: keyboard.press(key_brake)
    if enCruise: 
        keyboard.press_and_release(key_cruise)
        current_cruise = current_speed
    if upCruise: 
        keyboard.press_and_release(key_cruise_up)
        current_cruise += step
    if dwnCruise: 
        keyboard.press_and_release(key_cruise_dwn)
        current_cruise -= step

    if not accel: keyboard.release(key_accel)
    if not brake: keyboard.release(key_brake)

def OnKeyboardEvent(event):
    # print('MessageName:',event.MessageName)
    # print('Message:',event.Message)
    # print('Time:',event.Time)
    # print('Window:',event.Window)
    # print('WindowName:',event.WindowName)
    # print('Ascii:', event.Ascii, chr(event.Ascii))
    # print('Key:', event.Key)
    # print('KeyID:', event.KeyID)
    # print('ScanCode:', event.ScanCode)
    # print('Extended:', event.Extended)
    # print('Injected:', event.Injected)
    # print('Alt', event.Alt)
    # print('Transition', event.Transition)
    # print('---')

    if (event.WindowName == 'Euro Truck Simulator 2' and event.Key == 'Z'):
        #print('Key:', event.Key)
        global should_execute
        global dirty_ui
        global current_cruise
        dirty_ui = True
        should_execute = not should_execute
        if not should_execute: current_cruise = 0
        execute_commands(False, False, False, False, False)

# return True to pass the event to other handlers
    return True

# def pump_thread():
#     pythoncom.PumpMessages()

def cv_img_to_tk(src):
    img = cv2.cvtColor(src, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(img)    
    return ImageTk.PhotoImage(img)

def extract_current_speed():
    cur_raw =  sct.grab(current_speed_box)
    cur_speed_img = np.array(cur_raw)
    cur_speed_img = cv2.cvtColor(cur_speed_img, cv2.COLOR_RGB2GRAY)
    cur_speed_img = cv2.threshold(cur_speed_img, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    
    # t_grab_speed = perf_counter()-start_timer
    speed = -1
    try:
        current_ocr = pytesseract.image_to_string(cur_speed_img, config='--psm 7 --oem 3 -c tessedit_char_whitelist=0123456789')
        speed = int(re.match(digit_regex, current_ocr)[0])
    except:
        pass
    return speed, cur_speed_img
    # t_calc_speed = perf_counter()-start_timer

def extract_current_limit():
    limit_raw =  sct.grab(speed_limit_box)
    speed_limit_img = np.array(limit_raw)
    speed_limit_img = cv2.cvtColor(speed_limit_img, cv2.COLOR_RGB2GRAY)
    speed_limit_img = cv2.threshold(speed_limit_img, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    latest_limit_img = speed_limit_img
    # t_grab_limit = perf_counter()-start_timer
    limit = -1
    try:
        limit_ocr = pytesseract.image_to_string(speed_limit_img, config='--psm 8 --oem 3 -c tessedit_char_whitelist=0123456789')
        
        limit = int(re.match(digit_regex, limit_ocr)[0])
        
    except:
        pass

    return limit, speed_limit_img

def current_speed_thread():
    global current_speed
    global latest_speed_img
    global dirty_ui
    while running:
        prev_speed = current_speed
        (speed, latest_speed_img)  = extract_current_speed()
        if speed > 100 or speed < 0: speed = prev_speed # safety
        current_speed = speed
        if speed != prev_speed: dirty_ui = True

def speed_limit_thread():
    global speed_limit
    global latest_limit_img
    global dirty_ui
    while running:
        prev_limit = speed_limit
        (limit, latest_limit_img) = extract_current_limit()
        if limit > 100 or limit < 1: limit = prev_limit
        speed_limit = limit
        if limit != prev_limit: dirty_ui = True

def work_thread():
    global braking
    global accelerating
    global dirty_ui
    global current_cruise

    sleep_time = 1 / 30 # 30 ops per second, ideally

    counter = 5
    counter_timer = perf_counter()
    limit_count = 5
    
    while running:
        start_timer = perf_counter()
        counter += 1

        was_accel = accelerating
        was_brake = braking
        was_cruise = current_cruise > 0
        (accelerating, braking, enCruise, upCruise, dwnCruise) = determine_commands(current_speed, speed_limit, was_cruise, current_cruise)
        # t_determine = perf_counter()-start_timer
        if should_execute: 
            execute_commands(accelerating, braking, enCruise, upCruise, dwnCruise)
        # t_execute = perf_counter()-start_timer
        if was_accel != accelerating or was_brake != braking: dirty_ui = True
        if dirty_ui:
            en = 1 if should_execute else 0
            ac = 1 if accelerating else 0
            br = 1 if braking else 0
            log_file.write(f'{current_speed}, {speed_limit}, {current_cruise}, {en}, {ac}, {br}\n') # only need to log any changes
        # t_log = perf_counter()-start_timer
        end_timer = perf_counter()-start_timer
        if counter >= limit_count: # only check limit infrequently
            lps = limit_count / (perf_counter() - counter_timer)
            counter_timer = perf_counter()
            # print(f'LPS: {lps}')
            counter = 0
            #print(f'Loop time: {end_timer}\ngs:{start_timer} cs:{t_calc_speed-start_timer} gl:{t_grab_limit-t_calc_speed} cl:{t_calc_limit-t_grab_limit} det:{t_determine-t_calc_limit} ex:{t_execute-t_determine} log:{t_log-t_execute}')
            # print(f'Loop time: {end_timer}')
        # cv2.waitKey(50)
        sleep(sleep_time)

print(pytesseract.get_tesseract_version())

# create a hook manager
hm = pyWinhook.HookManager()
# watch for all keyboard events
hm.KeyDown = OnKeyboardEvent
# set the hook
hm.HookKeyboard()

sct = mss.mss()

#create a thread to process images/send commands
t_speed = threading.Thread(target=current_speed_thread)
t_speed.start()

t_limit = threading.Thread(target=speed_limit_thread)
t_limit.start()

t_worker = threading.Thread(target=work_thread)
t_worker.start()


enabled_lbl.pack()
cur_speed_lbl.pack()
speed_limit_lbl.pack()
cur_cruise_lbl.pack()
accel_lbl.pack()
braking_lbl.pack()
speed_img_lbl.pack()
limit_img_lbl.pack()

window.attributes('-topmost', True)
window.update()
# window.mainloop()

try:
    while running:
        # update UI
        if dirty_ui:
            enabled_lbl.configure(text=f'Enabled: {should_execute}')
            cur_speed_lbl.configure(text=f'Current: {current_speed}')
            speed_limit_lbl.configure(text=f'Limit: {speed_limit}')
            cur_cruise_lbl.configure(text=f'Cruise: {current_cruise}')
            accel_lbl.configure(text=f'Accelerating: {accelerating}')
            braking_lbl.configure(text=f'Braking: {braking}')

        if latest_speed_img is not None:
            copy = cv_img_to_tk(latest_speed_img)
            speed_img_lbl.configure(image=copy)
            speed_img_lbl.image = copy
            latest_speed_img = None

        if latest_limit_img is not None:
            copy_l = cv_img_to_tk(latest_limit_img)
            limit_img_lbl.configure(image=copy_l)
            limit_img_lbl.image = copy_l
            latest_limit_img = None
        window.update_idletasks()
        window.update()
        sleep(1/30)
except:
    running = False
    log_file.close()
    raise

#pythoncom.PumpMessages() # wait forever, passing keypresses along

#cv2.destroyAllWindows()

#TODO: Some sort of filtering to throw out random values that make no sense (91, random drops to single digits)
# Option for % offset rather than absolute (ie 5% is 4km/h at 80, 2 at 40, etc)
# UI options to change offset on the fly, other configuration