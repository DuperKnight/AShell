import os
from . import cd

aliases = ["mkdir"]
num_arguments = 1

def run(working_folder, *args):
    try:
        target = " ".join(args).strip()

        if not target:
            target = os.path.expanduser("~")

        target = os.path.expanduser(os.path.expandvars(target))

        if os.path.isabs(target):
            candidate = os.path.normpath(target)
        else:
            candidate = os.path.normpath(os.path.join(working_folder, target))
        os.mkdir(candidate)
        print(f"\n\n")
    except FileExistsError:
        print(f"mkdir: cannot create directory '{candidate}': File exists.")
    except PermissionError:
        print(f"mkdir: cannot create directory '{candidate}': Permission denied.")
    except Exception as e:
        print(f"mkdir: cannot create directory '{candidate}': {e}")