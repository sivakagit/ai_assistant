import os

# Drives to search

SEARCH_ROOTS = [
    "C:\\",
    "D:\\",
    "E:\\"
]

MAX_RESULTS = 10

last_search_results = []


def search_files(query):

    global last_search_results

    query = query.lower()

    matches = []

    for root_drive in SEARCH_ROOTS:

        if not os.path.exists(root_drive):
            continue

        for root, dirs, files in os.walk(root_drive):

            for name in files:

                # Ignore Windows shortcut files

                if name.endswith(".lnk"):
                    continue

                if query in name.lower():

                    full_path = os.path.join(
                        root,
                        name
                    )

                    matches.append(
                        full_path
                    )

                    if len(matches) >= MAX_RESULTS:

                        last_search_results = matches

                        return matches

    last_search_results = matches

    return matches