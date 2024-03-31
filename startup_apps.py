import argparse
import logging
import os
import subprocess
import time
import json


def validate_config(config):
    if not isinstance(config.get('startup_programs'), list):
        logging.error("The 'startup_programs' field in the config.json file should be a list of file paths.")
        return False
    for program in config.get('startup_programs'): 
        if not isinstance(program.get('path'), str) or not isinstance(program.get('delay'), (int, float)) or not isinstance(program.get('retry_delay'), (int, float)):
            logging.error("Each dictionary in the 'startup_programs' list should have a 'path' field (string) and a 'delay' field (number), and a 'retry_delay' field (number).")
            return False
    return True


parser = argparse.ArgumentParser(description="Run startup programs")
parser.add_argument("--config", type=str, default="config.json", help="Path to the config file")
args = parser.parse_args()

logging.basicConfig(filename='Startup Programs.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s', 
                    datefmt='%Y-%m-%d %H:%M:%S')

try:
    with open(args.config) as f:
        config = json.load(f)
except FileNotFoundError:
    logging.error(f"The config file '{args.config}' does not exist.")
    exit(1)

if not validate_config(config):
    exit(1)            

# List of startup programs
startup_programs = config['startup_programs']

try:
    delay = config['delay'] # Delay between each program execution (in seconds)
except KeyError:
    delay = 0    

logging.info(f"Waiting for {delay} seconds...")
time.sleep(delay)

MAX_RETRIES = 3

# Health check interval
HEALTH_CHECK_INTERVAL = 60  # in seconds

# List to store the processes
processes = []

# Loop through the startup programs
for program in startup_programs:
    for attempt in range(MAX_RETRIES):
        try:
            # Execute the program
            logging.info(f"Starting {program['path']} with arguments {program.get('args', '')}...")
            process = subprocess.Popen([program['path'] + program.get('args', '')])
            processes.append((program, process))

            # Wait for the specified delay
            delay = program['delay']
            logging.info(f"Waiting for {delay} seconds...")
            time.sleep(delay)
            break
        except FileNotFoundError:
            logging.error(f"Failed to start {program['path']}. Attempt {attempt + 1} of {MAX_RETRIES}. Please check if you have entered the correct file path in the config.json file.")
            if attempt == MAX_RETRIES - 1:  # No need to wait after the last attempt
                retry_delay = program['retry_delay']
                logging.info(f"Waiting for {retry_delay} seconds before retrying...")
                time.sleep(retry_delay)
            else:    
                logging.error(f"Failed to start {program['path']} after {MAX_RETRIES} attempts. Skipping to the next program.")

# Health check loop
while True:
    for program, process in processes:
        if process.poll() is not None:  # The process has terminated
            logging.warning(f"{program['path']} has stopped. Attempting to restart...")
            try:
                process = subprocess.Popen([program['path'] + program['args']])
            except FileNotFoundError:
                logging.error(f"Failed to restart {program['path']}. Please check if you have entered the correct file path in the config.json file.")
            else:
                logging.info(f"Successfully restarted {program['path']}.")
    time.sleep(HEALTH_CHECK_INTERVAL)  # Wait for a while before the next health check                
                  