import tkinter as tk
from tkinter import scrolledtext, ttk
import serial
import threading
import sys
import os
import re
import queue
import time  # Import time

# Add the project's root directory to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from backend import backend
except ModuleNotFoundError as e:
    print(f"Error: {e}")
    print("Ensure the project directory structure is correct and the script is run from the root directory.")
    sys.exit(1)


class SerialTesterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Serial Port Tester")
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.serial_port = None
        self.stop_threads = False  # Initialize BEFORE starting threads
        self.command_response_dict = {}
        self.button_widgets = {}
        self.status_labels = {}

        self.create_serial_display()
        self.create_button_area()
        self.connect_to_serial()

        self.response_buffer = ""
        self.last_command = ""
        self.prompt = "root@OpenWrt:/#"

    def create_serial_display(self):
        self.serial_display = scrolledtext.ScrolledText(
            self.root, wrap=tk.WORD, state=tk.DISABLED
        )
        self.serial_display.grid(row=0, column=1, sticky="nsew")
        self.serial_display.tag_config("error", foreground="red")
        self.serial_display.tag_config("success", foreground="green")  # tag for success

    def create_button_area(self):
        button_frame = ttk.Frame(self.root)
        button_frame.grid(row=0, column=0, sticky="nsew")

        button_data = backend.get_button_data()
        for button_info in button_data:
            text = button_info["text"]
            command = button_info["command"]
            row = button_info["row"]
            column = button_info["column"]
            expected_response = button_info.get("expected_response", None)  # Get expected response
            if command == "Clear Display":
                ttk.Button(
                    button_frame, text=text, command=self.clear_display
                ).grid(row=row, column=column, padx=5, pady=5, sticky="ew")
            else:
                btn = ttk.Button(
                    button_frame,
                    text=text,
                    command=lambda c=command, er=expected_response: self.send_command(c, er),
                )  # Pass expected response
                btn.grid(row=row, column=column, padx=5, pady=5, sticky="ew")
                self.command_response_dict[command] = expected_response  # store
                self.button_widgets[command] = btn  # Store the button widget

                # Create status label and store it
                status_label = ttk.Label(button_frame, text="Idle", foreground="orange")
                status_label.grid(
                    row=row, column=column + 1, padx=5, pady=5, sticky="ew"
                )  # Place label next to button
                self.status_labels[command] = status_label

        button_frame.grid_columnconfigure(0, weight=1)
        for i in range(len(button_data)):
            button_frame.grid_rowconfigure(i, weight=0)

    def connect_to_serial(self):
        try:
            serial_port = backend.get_serial_port()
            baud_rate = backend.get_baud_rate()
            timeout = backend.get_timeout()
            self.serial_port = serial.Serial(
                port=serial_port,
                baudrate=baud_rate,
                timeout=timeout,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                bytesize=serial.EIGHTBITS,
            )
            self.display_message(f"Connected to serial port: {serial_port}")
            threading.Thread(target=self.read_serial_data, daemon=True).start()
        except serial.SerialException as e:
            self.display_message(
                f"Error: Could not connect to serial port. {e}", "error"
            )

    def display_message(self, message, tag=None):
        self.serial_display.config(state=tk.NORMAL)
        self.serial_display.insert(tk.END, message + "\n", tag)
        self.serial_display.config(state=tk.DISABLED)
        self.serial_display.see(tk.END)

    def send_command(self, command, expected_response=None):  # Added expected_response
        if self.serial_port:
            try:
                self.serial_port.write(command.encode())
                self.display_message(f"Sent: {command}")
                self.response_buffer = ""
                self.last_command = command
                self.command_response_dict[command] = expected_response  # store expected response
                # set status to idle when command is sent.
                self.update_status_label(command, "Idle", "orange")
            except serial.SerialException as e:
                self.display_message(f"Error sending command: {e}", "error")
        else:
            self.display_message("Error: Not connected to a serial port.", "error")

    def clear_display(self):
        self.serial_display.config(state=tk.NORMAL)
        self.serial_display.delete("1.0", tk.END)
        self.serial_display.delete("1.0", tk.END)

    def read_serial_data(self):
        last_was_prompt = False

        while not self.stop_threads and self.serial_port and self.serial_port.is_open:
            try:
                data = (
                    self.serial_port.readline().decode("utf-8", errors="ignore").strip()
                )

                if data:
                    if data == self.last_command:
                        continue  # Ignore command echo

                    # Ignore displaying duplicated prompts
                    if data == self.prompt and last_was_prompt:
                        continue

                    self.display_message(data)
                    self.response_buffer += data + "\n"  # Append with newline for consistency

                    if data == self.prompt or data == self.prompt:
                        self.display_message("Prompt detected. Processing buffer.")
                        self.check_expected_response()
                        self.response_buffer = ""
                        last_was_prompt = True
                    else:
                        last_was_prompt = False

            except serial.SerialException as e:
                self.display_message(f"Error reading from serial port: {e}", "error")
                break
            except UnicodeDecodeError as e:
                self.display_message(f"Error decoding data: {e}", "error")
            except Exception as e:
                self.display_message(f"Error in read_serial_data: {e}", "error")
                break

        if self.serial_port:
            self.serial_port.close()
            self.display_message("Serial port closed.", "error")

    def check_expected_response(self):
        """Checks the full buffer only once after the prompt is detected."""
        expected_response = self.command_response_dict.get(self.last_command)

        if expected_response:
            self.display_message(
                f"Checking buffer: {self.response_buffer}"
            )  # Debugging message
            if expected_response in self.response_buffer:
                self.display_message(
                    f"Command: {self.last_command} - Passed", "success"
                )
                self.update_status_label(self.last_command, "Pass", "green")
            else:
                self.display_message(
                    f"Command: {self.last_command} - Failed. Expected: {expected_response}, Got:\n{self.response_buffer}",
                    "error",
                )
                self.update_status_label(self.last_command, "Fail", "red")

    def update_status_label(self, command, text, color):
        """Helper function to update the status label."""
        label = self.status_labels.get(command)
        if label:
            label.config(text=text, foreground=color)

    def on_closing(self):
        self.stop_threads = True
        if self.serial_port:
            self.serial_port.close()
        self.root.destroy()


if __name__ == "__main__":
    if "DISPLAY" not in os.environ:
        if os.name == "posix":
            os.environ["DISPLAY"] = ":0"
        else:
            print(
                "DISPLAY environment variable not set. This might cause issues on some systems."
            )
    root = tk.Tk()
    root.title("Serial Port Tester")  # Set the title here
    # Define a new style for success buttons.  Not used, but can be used if you want to change button appearence as well.
    style = ttk.Style(root)
    style.configure("Success.TButton", foreground="green")

    gui = SerialTesterGUI(root)
    root.protocol("WM_DELETE_WINDOW", gui.on_closing)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("Ctrl+C pressed. Cleaning up and exiting...")
        gui.on_closing()
        sys.exit(0)
