import os

from . import ls
from . import cd
from . import clear
from . import mkdir
from . import rm
from . import micro
from . import touch
from . import ashell


def _validate_num_arguments(cmd_module, args) -> bool:
    if cmd_module.num_arguments < len(args):
        print(f"{cmd_module.aliases[0]}: Expected {cmd_module.num_arguments} positional argument, got {len(args)} instead.")
        return False
    return True


def run(working_folder, command, *args):
    working_folder_path = os.fspath(working_folder)
    new_working_folder = working_folder_path

    match command:
        case _ if command in ls.aliases:
            cmd = ls
            if not _validate_num_arguments(cmd, args):
                return True, new_working_folder
            cmd.run(working_folder_path, *args)
            return True, new_working_folder

        case _ if command in cd.aliases:
            cmd = cd
            if not _validate_num_arguments(cmd, args):
                return True, new_working_folder
            result = cmd.run(working_folder_path, *args)
            if result:
                new_working_folder = result
            return True, new_working_folder

        case _ if command in clear.aliases:
            cmd = clear
            if not _validate_num_arguments(cmd, args):
                return True, new_working_folder
            cmd.run(working_folder_path, *args)
            return True, new_working_folder

        case _ if command in mkdir.aliases:
            cmd = mkdir
            if not _validate_num_arguments(cmd, args):
                return True, new_working_folder
            cmd.run(working_folder_path, *args)
            return True, new_working_folder

        case _ if command in rm.aliases:
            cmd = rm
            if not _validate_num_arguments(cmd, args):
                return True, new_working_folder
            cmd.run(working_folder_path, *args)
            return True, new_working_folder

        case _ if command in micro.aliases:
            cmd = micro
            if not _validate_num_arguments(cmd, args):
                return True, new_working_folder
            cmd.run(working_folder_path, *args)
            return True, new_working_folder

        case _ if command in touch.aliases:
            cmd = touch
            if not _validate_num_arguments(cmd, args):
                return True, new_working_folder
            cmd.run(working_folder_path, *args)
            return True, new_working_folder

        case _ if command in ashell.aliases:
            cmd = ashell
            if not _validate_num_arguments(cmd, args):
                return True, new_working_folder
            cmd.run(working_folder_path, *args)
            return True, new_working_folder

        case _:
            return False, new_working_folder