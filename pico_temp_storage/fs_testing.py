# main.py

import os


def main():
    print(os.statvfs("/"))
    # list all files in the root directory
    print(os.listdir("/"))

    # print the status of the root directory
    print(os.statvfs("/"))


if __name__ == "__main__":
    main()
