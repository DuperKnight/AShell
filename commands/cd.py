import os

aliases = ["cd", "goto"]
num_arguments = 1

def run(working_folder, *args):
    target = " ".join(args).strip()

    if not target:
        target = os.path.expanduser("~")

    target = os.path.expanduser(os.path.expandvars(target))

    if os.path.isabs(target):
        candidate = os.path.normpath(target)
    else:
        candidate = os.path.normpath(os.path.join(working_folder, target))

    if not os.path.exists(candidate):
        try:
            print(bcolors.FAIL + f"cd: no such file or directory: {target}" + bcolors.ENDC)
        except Exception:
            print(f"cd: no such file or directory: {target}")
        return working_folder

    if not os.path.isdir(candidate):
        try:
            print(bcolors.FAIL + f"cd: not a directory: {target}" + bcolors.ENDC)
        except Exception:
            print(f"cd: not a directory: {target}")
        return working_folder

    return candidate

class bcolors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    DIM = '\033[2m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

if __name__ == "__main__":
    run("/mnt/windows/Users/AESJB", "Documents")