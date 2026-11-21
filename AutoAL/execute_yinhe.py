import argparse
import subprocess
import pyautogui
import time
import json

# Function to execute the AutoIt script with given parameters
def execute_autoit_script(software, operation, symbols, account, password):
    # Start the AutoIt script
    autoit_process = subprocess.Popen(['C:\\Program Files (x86)\\AutoIt3\\AutoIt3.exe', 
                                       'c:\\Users\\admin\\Documents\\MCGA\\AutoAL\\yinhe089.au3'])
    time.sleep(5)  # Wait for the script to initialize

    # Focus on the opened window and send ALT+R
    pyautogui.hotkey('alt', 'r')
    time.sleep(1)  # Allow time for the action to take effect

    # # Automate GUI interactions using pyautogui
    # if software == "Yinhe":
    #     pyautogui.click(x=352, y=424)  # Select Yinhe software
    # elif software == "Huabao":
    #     pyautogui.click(x=352, y=448)  # Select Huabao software

    # # Input account credentials
    # pyautogui.typewrite(account)
    # pyautogui.press('tab')
    # pyautogui.typewrite(password)
    # pyautogui.press('enter')

    # # Select operation type
    # operation_map = {
    #     "Order": (208, 360),
    #     "Redeem": (208, 384),
    #     "Sell": (208, 408),
    #     "Cancel": (208, 432),
    #     "OrderOutTransfer": (208, 480),
    #     "OrderOut": (208, 504),
    #     "ConvertBond": (208, 528),
    #     "Allocate": (208, 552)
    # }
    # if operation in operation_map:
    #     x, y = operation_map[operation]
    #     pyautogui.click(x=x, y=y)

    # # Input fund symbols
    # for symbol in symbols:
    #     pyautogui.typewrite(symbol)
    #     pyautogui.press('enter')

    # # Execute the operation
    # pyautogui.click(x=672, y=552)  # Click the "Run" button

    # Wait for the process to complete
    time.sleep(10)
    # autoit_process.terminate()

# Main function to parse arguments and execute the script
def main():
    # Hardcoded JSON configuration inside the main function
    config = {
        "software": "Yinhe",
        "operation": "Order",
        "symbols": ["501300", "501312"],
        "account": "test_account",
        "password": "test_password"
    }

    # Extract parameters from the hardcoded JSON
    software = config.get("software")
    operation = config.get("operation")
    symbols = config.get("symbols", [])
    account = config.get("account")
    password = config.get("password")

    execute_autoit_script(software, operation, symbols, account, password)

if __name__ == "__main__":
    main()