import os
import mimetypes
from . import cd

aliases = ["ls", "dir"]
num_arguments = 2

colors = {
    "application": "\033[95m",
    "audio": "\033[96m",
    "font": "\033[94m",
    "example": "\033[90m",
    "image": "\033[92m",
    "message": "\033[93m",
    "model": "\033[91m",
    "multipart": "\033[97m",
    "text": "\033[93m",
    "video": "\033[35m",
}

def run(working_folder, *args):
    parts = []
    parsing_flags = True
    show_all = False
    for a in args:
        if parsing_flags and a == "--":
            parsing_flags = False
            continue
        if parsing_flags and a.startswith("-") and len(a) > 1:
            for ch in a[1:]:
                if ch in ("a", "A"):
                    show_all = True
                else:
                    pass
            continue
        parts.append(a)

    if len(parts) != 0:
        working_folder = cd.run(working_folder, parts[0])

    files = os.listdir(working_folder)

    if not show_all:
        files = [f for f in files if not f.startswith('.')]
    _files = []
    _folders = []

    print(bcolors.UNDERLINE + "Name" + bcolors.ENDC
           + " " * 26 + 
           bcolors.UNDERLINE + "Type" + bcolors.ENDC)
    
    for file in files:
        if os.path.isdir(working_folder + f"/{file}"):
            _folders.append(file)
        else:
            _files.append(file)


    for file in _folders:
        file_color = "\033[1;94m"
        
        if len(file) > 26:
            file = file[0:26] + "..."

        print(file_color + file + bcolors.ENDC, end='')

        size = 30 - len(file)
        i = 0
        while i - size != 0: 
            print("\033[90m" + "‧" + bcolors.ENDC, end='')
            i += 1

        print(file_color + f"Folder" + bcolors.ENDC)

    for file in _files:
        _, file_extension = os.path.splitext(file)
        mime_type, _ = mimetypes.guess_type("file" + file_extension)

        if mime_type != None:
            file_color = colors.get(mime_type.split("/")[0], '')
        else:
            file_color = "\033[37m"

        if len(file) > 26:
            file = file[0:26] + "..."

        print(file_color + file + bcolors.ENDC, end='')

        size = 30 - len(file)
        i = 0
        while i - size != 0: 
            print("\033[90m" + "‧" + bcolors.ENDC, end='')
            i += 1
        
        if file_extension == "":
            print("Binary/Unknown")
            continue

        print(file_color + f"{file_extension[1:]} ({mime_type})" + bcolors.ENDC)

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
    run("/mnt/windows/Users/AESJB/Documents/Server/server-files")