import threading
import time
import numpy as np
import serial
from warnings import warn 

class HSIEstimator():
    def __init__(self):
        # declare the parameters for the ports and baudrate
        self.port = '/dev/ttyAMA4'
        self.baudrate = 115200

        # some configuration for the ports
        self.ser_port = serial.Serial(
            self.port,
            self.baudrate,
            timeout=1,
            rtscts=True
        )

        # Variables defining port status
        self.port_active = False
        self.port_thread = None
        self.thread_lock = threading.Lock()

        # Variables for storing HSI configuration as stored in register 47
        # C is the C matrix in row-major order, 
        # B is the B vector
        self.hsi_before = {"C":[], 
                      "B":[]}
        
        self.hsi_after = {"C":[], 
                      "B":[]}

    # just gets the checksum in order to complete the raw message
    def vn_checksum(self, payload: str) -> str:
        x = 0
        for ch in payload.encode('ascii'):
            x ^= ch
        return f'{x:02X}'

    # completes the vectornav message with the raw message and checksum
    def write_full_vn_message(self, payload: str) -> bytes:
        cks = self.vn_checksum(payload)
        return f'${payload}*{cks}\r\n'.encode('ascii')

    def reader(self): 
        while self.port_active:
            try:
                msg = self.ser_port.readline().decode('ascii', errors='ignore').strip()
                if not msg:
                    # empty messages, skip this
                    continue
                parsed_msg = msg.split('*')[0].split(',')
                msg_type = parsed_msg[0].strip("$")
                # TODO: Add more message type handling
                # Check for the read register command for register 47(Storage for HSI Calibration)
                if msg_type == 'VNRRG' and int(parsed_msg[1]) == 47:
                    # if the before check hasn't been applied, this must be the first one. 
                    if not self.hsi_before['C']: 
                        self.hsi_before['C'] = parsed_msg[2:11]
                        self.hsi_before['B'] = parsed_msg[11:14]
                    elif not self.hsi_after['C']:
                        self.hsi_after['C'] = parsed_msg[2:11]
                        self.hsi_after['B'] = parsed_msg[11:14]
                    else: 
                        warn("HSI Requested more than 2 times. Something is wrong!")

                elif msg_type == 'VNERR':
                    # there is some error in the vn100, print it to the logger
                    warn(
                        f'Error code {parsed_msg[1]} in vn100 node'
                    )

                else:
                    # We don't really care about other messages in this program, so just continue
                    print(f"Unhandled Message: {msg}")

            except Exception as e:
                print(f'Error in Port 1: {e}')

        print('Serial Port 1 Closing')
        return

    def check_to_continue(self):
        while True: 
            try: 
                passed = input('Would you like to continue? (y/n): ')
                if passed == 'y': 
                    return True
                if passed == 'n':
                    return False
                else: 
                    print("Invalid Response! Try Again...")
            except KeyboardInterrupt: 
                print("Breaking out of checking loop and stopping program...")
                return False

    def start_reading_threads(self):
        # Bring up both threads
        try: 
            with self.thread_lock:
                if not self.port_active:
                    self.port_active = True

                    if self.port_thread is None or not self.port_thread.is_alive():
                        self.port_thread = threading.Thread(
                            target=self.reader,
                            daemon=True
                        )
                        self.port_thread.start()
                        print('Started Port 1 reading thread')
        except Exception as e:
            print(f'Exception! {e}')

    def stop_reading_threads(self):
        # Bring down both threads
        with self.thread_lock:
            if self.port_active:
                self.port_active = False

                if self.port_thread and self.port_thread.is_alive():
                    self.port_thread.join(timeout=2.0)


    def run_hsi_calibration(self):
        # Step 0: Set async data frequency to 0 so we can see all messages on port 1
        print("Turning Serial Port Async Messages Off")
        freq_off_msg = self.write_full_vn_message('VNWRG,07,0,1')
        self.ser_port.write(freq_off_msg)

        # Step 1: Check the value of the hsi register for a baseline
        print("Checking Value for HSI Parameters Currently")
        check_hsi_msg = self.write_full_vn_message(f"VNRRG,47")
        self.ser_port.write(check_hsi_msg)

        t_start = time.time()
        t_now = time.time()
        timeout = 15 # seconds
        # wait until hsi has been updated
        while (not self.hsi_before['C']) and (t_now - t_start < timeout):
            t_now = time.time()
        if self.hsi_before['C']:
            print("HSI has been updated. Values are:")

            print(f"C = [{self.hsi_before['C'][0]},{self.hsi_before['C'][1]},{self.hsi_before['C'][2]}]\n"
                  f"    [{self.hsi_before['C'][3]},{self.hsi_before['C'][4]},{self.hsi_before['C'][5]}]\n"
                  f"    [{self.hsi_before['C'][6]},{self.hsi_before['C'][7]},{self.hsi_before['C'][8]}]\n]")
            
            print(f"B = [{self.hsi_before['B'][0]}, {self.hsi_before['B'][1]}, {self.hsi_before['B'][2]}]")

        cont = self.check_to_continue()
        if not cont: 
            print("Stopping Before The HSI Estimation Step")
            return 
        
        # Step 2: Send the message to start the hsi estimation process 
        print("Moving on to HSI Estiamtion Step")
        getting_input = True
        while getting_input: 
            try:
                conv_rate = input("What convergence rate would you like? (1-5): ")
                if float(conv_rate) <= 5 and float(conv_rate) >= 1: 
                    getting_input = False
                    start_msg = self.write_full_vn_message(f"VNWRG,44,1,1,{conv_rate}")
                    self.ser_port.write(start_msg)
                else: 
                    warn("Invalid Convergence Rate! It must be between 1 and 5! Give it another shot.")
            except KeyboardInterrupt: 
                print("HSI Input Never Gathered. Stopping Program...")

        # Step 3: Wait for about 120 seconds for hsi to converge as we spin the robot 
        print("Waiting 2min for the HSI estimation process to complete.")
        print("While this is running, please rotate the vehicle in all axes, trying to go through all positions")
        wait_time = 120 
        time.sleep(wait_time)

        # Step 4: Check the value of the HSI register again 
        self.ser_port.write(check_hsi_msg)

        t_start = time.time()
        t_now = time.time()
        timeout = 15 # seconds
        # wait until hsi has been updated
        while (not self.hsi_after['C']) and (t_now - t_start < timeout):
            t_now = time.time()
        if self.hsi_after['C']:
            print("HSI has been updated. Values are:")

            print(f"C = [{self.hsi_after['C'][0]},{self.hsi_after['C'][1]},{self.hsi_after['C'][2]}]\n"
                  f"    [{self.hsi_after['C'][3]},{self.hsi_after['C'][4]},{self.hsi_after['C'][5]}]\n"
                  f"    [{self.hsi_after['C'][6]},{self.hsi_after['C'][7]},{self.hsi_after['C'][8]}]\n]")
            
            print(f"B = [{self.hsi_after['B'][0]}, {self.hsi_after['B'][1]}, {self.hsi_after['B'][2]}]")
        
        # Step 5: Stop the estimation process, apply changes if asked
        print("Stopping the estimation process and applying changes to the measurements.")
        start_msg = self.write_full_vn_message(f"VNWRG,44,0,3,1")
        self.ser_port.write(start_msg)

        # Step 6: Save the register(if we want to)
        print("Moving on to save the register.")
        cont = self.check_to_continue()
        if not cont: 
            print("Stopping Before Saving the Results!")
            return 
        
        reset_async_output = self.write_full_vn_message("VNWRG,7,40,1") # back to 40Hz
        self.ser_port.write(reset_async_output)

        # now wait a second and save the data: 
        time.sleep(1)
        save_settings_msg = self.write_full_vn_message("VNWNV")
        self.ser_port.write(save_settings_msg)
        print("HSI process has completed and saved. Have a good day and good luck!")
        return 

def main(args=None):
    #Instantiate the HSI Estimator
    estimator = HSIEstimator()

    #First, start the reading thread
    estimator.start_reading_threads()

    #Now, run the series of commands for hsi calibration
    estimator.run_hsi_calibration()
    #Now, stop reading threads
    estimator.stop_reading_threads()

if __name__ == '__main__':
    main()
