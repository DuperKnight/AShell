import os
import shutil

aliases = ["rm"]
num_arguments = 3


def _refuse_reason(candidate, working_folder):
    cand = os.path.normpath(candidate)
    root = os.path.normpath(os.sep)
    home = os.path.normpath(os.path.expanduser("~"))
    working = os.path.normpath(working_folder)

    if cand == root:
        return False, "refuse to remove root directory '/'"
    if cand == home:
        return False, "refuse to remove your home directory"

    if cand == working:
        return False, "refuse to remove the current working directory"

    return True, None


def run(working_folder, *args):
    parts = []
    recursive = False
    force = False
    parsing_flags = True
    for a in args:
        if parsing_flags and a == "--":
            parsing_flags = False
            continue
        if parsing_flags and a.startswith("-") and len(a) > 1:
            for ch in a[1:]:
                if ch in ("r", "R"):
                    recursive = True
                elif ch == "f":
                    force = True
                else:
                    pass
            continue
        parts.append(a)

    if not parts:
        print("rm: missing operand")
        return

    target = " ".join(parts).strip()
    target = os.path.expanduser(os.path.expandvars(target))

    if os.path.isabs(target):
        candidate = os.path.normpath(target)
    else:
        candidate = os.path.normpath(os.path.join(working_folder, target))

    ok, reason = _refuse_reason(candidate, working_folder)
    if not ok:
        print(f"rm: {reason}.")
        return

    if not os.path.exists(candidate):
        if not force:
            print(f"rm: cannot remove '{candidate}': No such file or directory")
        return

    try:
        is_dir = os.path.isdir(candidate) and not os.path.islink(candidate)
    except Exception:
        is_dir = False

    if is_dir:
        if not recursive:
            print(f"rm: cannot remove '{candidate}': Is a directory")
            return

        if not force:
            try:
                ans = input(f"rm: remove directory '{candidate}' recursively? [y/N] ")
            except Exception:
                ans = "n"
            if ans.lower() not in ("y", "yes"):
                print("rm: aborted")
                return

        try:
            shutil.rmtree(candidate)
            print("\n")
        except PermissionError:
            print(f"rm: cannot remove '{candidate}': Permission denied.")
        except Exception as e:
            print(f"rm: cannot remove '{candidate}': {e}")
        return

    if not force:
        try:
            ans = input(f"rm: remove file '{candidate}'? [y/N] ")
        except Exception:
            ans = "n"
        if ans.lower() not in ("y", "yes"):
            print("rm: aborted")
            return

    try:
        os.remove(candidate)
        print("\n")
    except PermissionError:
        print(f"rm: cannot remove '{candidate}': Permission denied.")
    except Exception as e:
        print(f"rm: cannot remove '{candidate}': {e}")