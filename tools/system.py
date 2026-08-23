import platform
import os
import sys


def get_system_info():
    info = {
        "operating_system": platform.system(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "computer_name": platform.node(),
        "python_version": sys.version.split()[0],
        "username": os.getlogin()
    }

    return info


if __name__ == "__main__":
    information = get_system_info()

    for key, value in information.items():
        print(f"{key}: {value}")