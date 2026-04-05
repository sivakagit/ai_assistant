import platform
import psutil


def get_cpu_usage():

    return psutil.cpu_percent(interval=1)


def get_ram_usage():

    memory = psutil.virtual_memory()

    used_gb = memory.used / (1024 ** 3)

    total_gb = memory.total / (1024 ** 3)

    percent = memory.percent

    return used_gb, total_gb, percent


def get_battery_status():

    battery = psutil.sensors_battery()

    if battery is None:

        return "Battery information not available"

    percent = battery.percent

    plugged = battery.power_plugged

    status = "Charging" if plugged else "Not Charging"

    return f"{percent}% ({status})"


def get_system_info():

    cpu = get_cpu_usage()

    ram_used, ram_total, ram_percent = get_ram_usage()

    battery = get_battery_status()

    system = platform.system()

    release = platform.release()

    processor = platform.processor()

    info = []

    info.append(f"System: {system} {release}")

    info.append(f"Processor: {processor}")

    info.append(f"CPU Usage: {cpu}%")

    info.append(
        f"RAM Usage: {ram_used:.2f} GB / {ram_total:.2f} GB ({ram_percent}%)"
    )

    info.append(f"Battery: {battery}")

    return "\n".join(info)