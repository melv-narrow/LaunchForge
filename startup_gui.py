import tkinter as tk
from tkinter import messagebox
import startup_apps as main

# Create the main window
root = tk.Tk()

# Create a row for each program
for i, program in enumerate(main.startup_programs):
    # Create a label for the program name
    name_label = tk.Label(root, text=program['path'])
    name_label.grid(row=i, column=0)

    # Create a label for the program status
    status_label = tk.Label(root, text=main.get_programs_status()[i])
    status_label.grid(row=i, column=1)

    # Create a start button for the program
    start_button = tk.Button(root, text="Start", command=lambda program=program, status_label=status_label: start_program(program, status_label))
    start_button.grid(row=i, column=2)

    # Create a stop button for the program
    stop_button = tk.Button(root, text="Stop", command=lambda program=program, status_label=status_label: stop_program(program, status_label))
    stop_button.grid(row=i, column=3)

# Define the function to start a program
def start_program(program, status_label):
    try:
        # Start the program
        main.start_program(program)

        # Update the status label
        status_label.config(text="Running")
    except FileNotFoundError:
        messagebox.showerror("Error", f"Failed to start {program['path']}. Please check if you have entered the correct file path in the config.json file.")

# Define the function to stop a program
def stop_program(program, status_label):
    # Stop the program
    main.stop_program(program)

    # Update the status label
    status_label.config(text="Not running")

# Start the main loop
root.mainloop()