import os

import numpy as np
import cv2
import imutils
# from PIL import ImageGrab
from PIL import Image, ImageTk
import keyboard
import pytesseract
import re
import pythoncom, pyWinhook
import threading
from time import sleep

import tkinter as tk

import mss

digit_regex = r'\d+'

current_speed_box = (1490, 710, 1525, 730)
speed_limit_box = (1500, 780, 1525, 805)

key_accel = 'w'
key_brake = 's'

should_execute = False
running = True

current_speed = 0
speed_limit = 0
braking = False
accelerating = False

log_file = open('log.csv', 'w')
log_file.write('Speed, Limit, Enabled, Accel, Brake\n')

# UI elements
dirty_ui = False
latest_speed_img = None
latest_limit_img = None

window = tk.Tk()
enabled_lbl = tk.Label(text=f'Enabled: {should_execute}')
cur_speed_lbl = tk.Label(text=f'Current: {current_speed}')
speed_limit_lbl = tk.Label(text=f'Limit: {speed_limit}')
accel_lbl = tk.Label(text=f'Accelerating: {accelerating}')
braking_lbl = tk.Label(text=f'Braking: {braking}')
speed_img_lbl = tk.Label()
limit_img_lbl = tk.Label()
# /UI elements

def determine_commands(current, limit):
    accelerate = (current < limit)
    brake = (current > (limit + 5))
    # print(f'Accel: {accelerate} Brake: {brake}')
    return accelerate, brake


def execute_commands(accel, brake):
    if accel: keyboard.press(key_accel)
    if brake: keyboard.press(key_brake)

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
        dirty_ui = True
        should_execute = not should_execute
        execute_commands(False, False)

# return True to pass the event to other handlers
    return True

# def pump_thread():
#     pythoncom.PumpMessages()

def cv_img_to_tk(src):
    img = cv2.cvtColor(src, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(img)    
    return ImageTk.PhotoImage(img)

def work_thread():
    global current_speed
    global speed_limit
    global braking
    global accelerating
    global latest_speed_img
    global latest_limit_img
    global dirty_ui

    sct = mss.mss()
    while running:
        # img_orig = cv2.imread('Sample_1.jpg')
        
        #cur_raw = ImageGrab.grab(bbox=current_speed_box)
        cur_raw =  sct.grab(current_speed_box)
        cur_speed_img = np.array(cur_raw)
        cur_speed_img = cv2.cvtColor(cur_speed_img, cv2.COLOR_RGB2GRAY)
        cur_speed_img = cv2.threshold(cur_speed_img, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]

        latest_speed_img = cur_speed_img

        #limit_raw = ImageGrab.grab(bbox=speed_limit_box)
        limit_raw =  sct.grab(speed_limit_box)
        speed_limit_img = np.array(limit_raw)
        speed_limit_img = cv2.cvtColor(speed_limit_img, cv2.COLOR_RGB2GRAY)
        speed_limit_img = cv2.threshold(speed_limit_img, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

        latest_limit_img = speed_limit_img
        # cur_speed_img = img_orig[current_speed_box[1]:current_speed_box[3], current_speed_box[0]:current_speed_box[2]]
        # speed_limit_img = img_orig[speed_limit_box[1]:speed_limit_box[3], speed_limit_box[0]:speed_limit_box[2]]
        # cv2.imshow('img', img_orig)

        try:
            current_ocr = pytesseract.image_to_string(cur_speed_img, config='--psm 10 --oem 3 -c tessedit_char_whitelist=0123456789')
            prev_speed = current_speed
            current_speed = int(re.match(digit_regex, current_ocr)[0])
            if current_speed > 100 or current_speed < 0: current_speed = prev_speed # safety
            # cv2.imshow('current', cur_speed_img)
            #print(current)
            if current_speed != prev_speed: dirty_ui = True
        except:
            pass
        try:
            limit_ocr = pytesseract.image_to_string(speed_limit_img, config='--psm 10 --oem 3 -c tessedit_char_whitelist=0123456789')
            prev_limit = speed_limit
            speed_limit = int(re.match(digit_regex, limit_ocr)[0])
            if speed_limit > 100 or speed_limit < 1: speed_limit = prev_limit
            if speed_limit != prev_limit: dirty_ui = True
            # cv2.imshow('limit', speed_limit_img)
        except:
            pass
            #print('Could not find current/limit speed')
        # print(f'current: {current_speed} limit: {speed_limit}')
        was_accel = accelerating
        was_brake = braking
        (accelerating, braking) = determine_commands(current_speed, speed_limit)
        if should_execute: execute_commands(accelerating, braking)
        if was_accel != accelerating or was_brake != braking: dirty_ui = True
        if dirty_ui: 
            en = 1 if should_execute else 0
            ac = 1 if accelerating else 0
            br = 1 if braking else 0
            log_file.write(f'{current_speed}, {speed_limit}, {en}, {ac}, {br}\n') # only need to log any changes
            
        
        # cv2.waitKey(50)

# create a hook manager
hm = pyWinhook.HookManager()
# watch for all keyboard events
hm.KeyDown = OnKeyboardEvent
# set the hook
hm.HookKeyboard()

#create a thread to process images/send commands
thread = threading.Thread(target=work_thread)
thread.start()

enabled_lbl.pack()
cur_speed_lbl.pack()
speed_limit_lbl.pack()
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

#TODO: Put braking on a PID or something because it *way* overshoots. Probably only needs a short tap most of the time