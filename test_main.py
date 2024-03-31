import logging
from main import validate_config

def test_validate_config():
    # Test case 1: Valid config
    config1 = {
        'startup_programs': ['/path/to/program1', '/path/to/program2'],
        'delay': 5
    }
    assert validate_config(config1) == True

    # Test case 2: Invalid 'startup_programs' field
    config2 = {
        'startup_programs': 'invalid',
        'delay': 5
    }
    assert validate_config(config2) == False
    assert logging.error.call_args[0][0] == "The 'startup_programs' field in the config.json file should be a list of file paths."

    # Test case 3: Invalid 'delay' field
    config3 = {
        'startup_programs': ['/path/to/program1', '/path/to/program2'],
        'delay': 'invalid'
    }
    assert validate_config(config3) == False
    assert logging.error.call_args[0][0] == "The 'delay' field in the config.json file should be a number representing the delay between program executions."

    # Test case 4: Missing 'startup_programs' field
    config4 = {
        'delay': 5
    }
    assert validate_config(config4) == False
    assert logging.error.call_args[0][0] == "The 'startup_programs' field is missing in the config.json file."

    # Test case 5: Missing 'delay' field
    config5 = {
        'startup_programs': ['/path/to/program1', '/path/to/program2']
    }
    assert validate_config(config5) == False
    assert logging.error.call_args[0][0] == "The 'delay' field is missing in the config.json file."

test_validate_config()