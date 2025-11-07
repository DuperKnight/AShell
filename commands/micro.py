import os
import shutil
import subprocess

aliases = ["micro", "edit"]
num_arguments = 1


def run(working_folder, *args):
    editor = shutil.which("micro")
    fallback = None
    if not editor:
        env_editor = os.environ.get("EDITOR")
        if env_editor:
            parts = env_editor.split()
            fallback = shutil.which(parts[0])
            fallback_cmd = parts if parts else None

    cmd = None
    if editor:
        cmd = [editor] + list(args)
    elif fallback:
        cmd = fallback_cmd + list(args)
    else:
        print("micro: 'micro' is not installed and $EDITOR is not set or unavailable.")
        print("Install micro or set the EDITOR environment variable to your preferred editor.")
        return

    try:
        result = subprocess.run(cmd, cwd=working_folder)
        if result.returncode != 0:
            print(f"micro: editor exited with return code {result.returncode}")
    except FileNotFoundError:
        print("micro: command not found or could not be executed.")
    except Exception as e:
        print(f"micro: An error occurred: {e}")