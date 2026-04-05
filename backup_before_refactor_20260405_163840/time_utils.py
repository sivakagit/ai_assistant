from datetime import datetime


def get_current_time():

    now = datetime.now()

    return now.strftime(
        "Current time: %H:%M:%S"
    )


def get_current_date():

    today = datetime.now()

    return today.strftime(
        "Today's date: %Y-%m-%d"
    )