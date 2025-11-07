import subprocess

aliases = ["clear"]
num_arguments = 0

def run(working_folder, *args):
    try:
        subprocess.run(["clear"])
    except Exception:
        print("\033[H\033[J", end='')