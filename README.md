## LaunchForge Program

### Introduction
The LaunchForge program is a Python script designed to manage and execute a list of startup programs defined in a configuration file. It provides functionalities to start these programs with specified delays and retry mechanisms. The program also includes a health check loop to monitor the status of the executed processes and restart them if necessary.

### Features
- Configurable startup programs with delay and retry settings.
- Automatic health check and restart functionality.
- Detailed logging for monitoring program execution.

### Requirements
- Python 3.x
- argparse library
- logging library

### Installation
1. Clone or download the repository containing the LaunchForge program.
2. Ensure Python 3.x is installed on your system.
3. Install the required libraries using pip:
   ```
   pip install argparse
   ```
4. Navigate to the directory containing the program files.

### Usage
```
python startup_apps.py [--config CONFIG_FILE]
```

- `--config`: Path to the config file (default: `config.json`)

### Configuration File (config.json)
The configuration file should is in JSON format and includes the following fields:
- `startup_programs`: List of startup programs, each defined with the following attributes:
  - `path`: Path to the executable file.
  - `args` (optional): Command-line arguments for the program.
  - `delay`: Delay (in seconds) before starting the program.
  - `retry_delay`: Delay (in seconds) before retrying to start the program in case of failure.
- `delay` (optional): Delay (in seconds) before starting the first program.

Example `config.json`:
```json
{
  "startup_programs": [
    {
      "path": "program1.exe",
      "delay": 5,
      "retry_delay": 10
    },
    {
      "path": "program2.py",
      "args": "--arg1 value1 --arg2 value2",
      "delay": 10,
      "retry_delay": 15
    }
  ],
  "delay": 30
}
```

### Logging
The program logs detailed information to a file named `Startup Programs.log` in the following format:
```
[timestamp] - [level] - [message]
```

- `timestamp`: Date and time of the log entry.
- `level`: Severity level of the log entry (e.g., INFO, ERROR).
- `message`: Log message providing information about program execution.

### Using Startup Folder to start LaunchForge
`Open Startup Folder`: Press Windows + R to open the Run dialog, then type shell:startup and hit Enter. This will open the Startup folder.

`Create Shortcut`:
 - Right-click inside the Startup folder and select "New" > "Shortcut".
 - In the "Create Shortcut" wizard, click "Browse" and navigate to the Python executable (python.exe) installed on your system.
 - Select the Python executable and click "Next".
 - In the "Type the location of the item" field, append the full path to the LaunchForge script (launchforge.py) separated by a space.
 - Click "Next" and provide a name for the shortcut (e.g., "LaunchForge").
 - Click "Finish" to create the shortcut.

`Verification`:
 - Restart your computer or log out and log back in to test if LaunchForge launches automatically.
 - Verify that LaunchForge starts along with Windows by checking if your configured startup programs are launched.

### License
This program is licensed under the MIT License. See the `LICENSE` file for details.

