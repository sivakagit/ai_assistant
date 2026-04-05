import os

PACKAGES = [
    "core",
    "services",
    "tools",
    "ui",
    "models",
    "install",
    "patches",
    "data",
    "infrastructure",
    "backup",
    "workspace"
]

def create_init_files():

    for folder in PACKAGES:

        path = os.path.join(folder, "__init__.py")

        if not os.path.exists(path):

            with open(path, "w") as f:
                f.write("# package")

            print("Created:", path)

if __name__ == "__main__":

    create_init_files()