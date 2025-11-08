from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import os
import readline
import re
import shlex
import shutil
import subprocess

_CURRENT_WORKING_FOLDER = os.getcwd()


def set_current_working_folder(path: os.PathLike[str] | str) -> None:
    global _CURRENT_WORKING_FOLDER
    _CURRENT_WORKING_FOLDER = os.fspath(path)


def get_current_working_folder() -> str:
    return _CURRENT_WORKING_FOLDER


@dataclass(frozen=True)
class CommandSpec:
    name: str
    aliases: tuple[str, ...]
    flags: tuple[str, ...] = ()
    takes_path: bool = False


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec("help", ("help",)),
    CommandSpec("exit", ("exit",)),
    CommandSpec("reload", ("reload",), ("--full", "--hard", "--all", "-f", "-a")),
    CommandSpec("clear", ("clear",)),
    CommandSpec("cd", ("cd", "goto"), (), True),
    CommandSpec("ls", ("ls", "dir"), ("-a", "-A", "--all", "--"), True),
    CommandSpec("mkdir", ("mkdir",), (), True),
    CommandSpec("touch", ("touch",), (), True),
    CommandSpec("rm", ("rm",), ("-f", "-r", "-R", "-rf", "-fr", "--"), True),
    CommandSpec("micro", ("micro",), (), True),
    CommandSpec("ashell", ("ashell",), ("upgrade"))
)

COMMAND_BY_ALIAS: dict[str, CommandSpec] = {}
for spec in COMMAND_SPECS:
    for alias in spec.aliases:
        COMMAND_BY_ALIAS[alias] = spec

ALL_COMMAND_ALIASES: tuple[str, ...] = tuple(sorted(COMMAND_BY_ALIAS))

ESCAPE_CHARS = set(" \t\n\\'\"$`&|;<>*?()[]{}!")
HELP_TOKEN_STRIP = ".,;:()[]{}<>|\"'"

EXTERNAL_FLAG_CACHE: dict[str, tuple[str, ...]] = {}
EXTERNAL_POSITIONAL_CACHE: dict[str, tuple[str, ...]] = {}
EXTERNAL_POSITIONAL_TREE: dict[str, dict[tuple[str, ...], tuple[str, ...]]] = {}
EXTERNAL_METADATA_ATTEMPTED: set[str] = set()
EXTERNAL_PREFIX_ATTEMPTED: dict[str, set[tuple[str, ...]]] = {}
EXTERNAL_HELP_SWITCHES: tuple[str, ...] = ("--help", "-h", "-?", "help")
EXTERNAL_CONTEXT_SWITCHES: tuple[tuple[str, ...], ...] = (("--help",), ("help",), ("-h",))
EXTERNAL_HELP_TIMEOUT = 1.5
EXTERNAL_STOP_WORDS: set[str] = {
    "usage",
    "options",
    "option",
    "argument",
    "arguments",
    "command",
    "commands",
    "object",
    "objects",
    "help",
    "examples",
    "example",
    "description",
    "available",
    "list",
    "show",
    "when",
    "where",
}


def _gather_path_executables() -> tuple[str, ...]:
    seen: set[str] = set()
    executables: list[str] = []
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.name in seen:
                        continue
                    try:
                        if not entry.is_file():
                            continue
                    except OSError:
                        continue
                    try:
                        if not os.access(entry.path, os.X_OK):
                            continue
                    except OSError:
                        continue
                    seen.add(entry.name)
                    executables.append(entry.name)
        except OSError:
            continue
    executables.sort()
    return tuple(executables)


PATH_EXECUTABLES = _gather_path_executables()


def refresh_executable_cache() -> None:
    global PATH_EXECUTABLES
    PATH_EXECUTABLES = _gather_path_executables()


def _split_prefix(fragment: str) -> tuple[str, str]:
    if not fragment:
        return "", ""
    slash_index = fragment.rfind("/")
    if slash_index == -1:
        return "", fragment
    return fragment[: slash_index + 1], fragment[slash_index + 1 :]


def _resolve_lookup_dir(prefix: str, working_dir: str) -> str:
    expanded = os.path.expanduser(os.path.expandvars(prefix)) if prefix else ""
    if not expanded:
        return working_dir
    if os.path.isabs(expanded):
        return os.path.normpath(expanded)
    return os.path.normpath(os.path.join(working_dir, expanded))


def _unescape_fragment(value: str) -> str:
    if not value:
        return value
    result: list[str] = []
    escaping = False
    for ch in value:
        if escaping:
            result.append(ch)
            escaping = False
            continue
        if ch == "\\":
            escaping = True
            continue
        result.append(ch)
    if escaping:
        result.append("\\")
    return "".join(result)


def _escape_fragment(value: str) -> str:
    if not value:
        return value
    escaped: list[str] = []
    for ch in value:
        if ch in ESCAPE_CHARS:
            escaped.append("\\" + ch)
        else:
            escaped.append(ch)
    return "".join(escaped)


def _segment_for_hidden(prefix: str, partial: str) -> str:
    if partial:
        return partial
    trimmed = prefix.rstrip("/")
    if not trimmed:
        return ""
    return trimmed.split("/")[-1]


def _should_include_hidden(prefix: str, partial: str) -> bool:
    segment = _segment_for_hidden(prefix, partial)
    return segment.startswith(".")


def _looks_like_path(fragment: str) -> bool:
    if not fragment:
        return False
    stripped = fragment.lstrip("'\"")
    if not stripped:
        return False
    if stripped.startswith(("./", "../", "~/", "/")):
        return True
    return "/" in stripped or stripped.startswith(".")


def _split_tokens(text: str) -> list[str]:
    if not text:
        return []
    lexer = shlex.shlex(text, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    try:
        return list(lexer)
    except ValueError:
        return text.split()


def _build_help_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PAGER", "cat")
    env.setdefault("MANPAGER", "cat")
    env.setdefault("GIT_PAGER", "cat")
    env.setdefault("LC_ALL", "C")
    return env


def _format_path_candidate(unescaped: str, quote_char: str) -> str:
    if quote_char:
        return quote_char + unescaped
    return _escape_fragment(unescaped)


def _unique_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def complete_path(fragment: str, working_dir: str) -> list[str]:
    fragment = fragment or ""
    quote_char = fragment[0] if fragment and fragment[0] in ("'", '"') else ""
    body = fragment[1:] if quote_char else fragment

    unescaped_body = _unescape_fragment(body)
    prefix_unescaped, partial_unescaped = _split_prefix(unescaped_body)
    lookup_dir = _resolve_lookup_dir(prefix_unescaped, working_dir)

    include_hidden = _should_include_hidden(prefix_unescaped, partial_unescaped)
    candidates: list[str] = []

    try:
        with os.scandir(lookup_dir) as entries:
            for entry in entries:
                name = entry.name
                if not include_hidden and name.startswith('.'):
                    continue
                if not name.startswith(partial_unescaped):
                    continue
                candidate_unescaped = prefix_unescaped + name
                try:
                    if entry.is_dir():
                        candidate_unescaped += "/"
                except OSError:
                    pass
                candidates.append(_format_path_candidate(candidate_unescaped, quote_char))
    except OSError:
        return []

    ordered = _unique_preserving_order(candidates)
    ordered.sort(key=lambda item: (0 if item.endswith("/") else 1, item))
    return ordered


def _extract_flags_from_text(output: str) -> set[str]:
    if not output:
        return set()
    pattern = re.compile(r"(?<![\w-])(--?[\w?][\w-]*)")
    matches: set[str] = set()
    for token in pattern.findall(output):
        cleaned = token.rstrip(".,;:)")
        if cleaned:
            matches.add(cleaned)
    return matches


def _extract_positionals_from_text(output: str, command_name: str) -> set[str]:
    if not output:
        return set()

    tokens: set[str] = set()
    command_lower = command_name.lower()

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        lower = stripped.lower()
        if lower.startswith("usage") or lower.startswith("synopsis"):
            continue
        if stripped.startswith("-"):
            continue
        if stripped.endswith(":") and " " not in stripped:
            continue

        parts = stripped.split()
        if parts and parts[0].lower() == command_lower:
            parts = parts[1:]

        for part in parts:
            normalized = _normalize_help_token(part, command_lower)
            if normalized:
                tokens.add(normalized)

        if len(tokens) >= 128:
            break

    return tokens


def _normalize_help_token(token: str, command_lower: str) -> str | None:
    stripped = token.strip(HELP_TOKEN_STRIP)
    if not stripped:
        return None

    stripped = stripped.replace("[", "").replace("]", "")
    if not stripped or stripped.startswith("-"):
        return None

    lower = stripped.lower()
    if lower == command_lower or lower in EXTERNAL_STOP_WORDS:
        return None
    if len(lower) <= 1:
        return None
    if not any(ch.isalpha() for ch in stripped):
        return None
    if stripped.isupper():
        return None
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9._-]*", stripped):
        return None

    return stripped


def _build_positional_tree(output: str, command_name: str) -> dict[tuple[str, ...], set[str]]:
    tree: dict[tuple[str, ...], set[str]] = defaultdict(set)
    if not output:
        return tree

    command_lower = command_name.lower()

    for raw_line in output.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        head = stripped.split()[0]
        normalized_head = _normalize_help_token(head, command_lower)
        if normalized_head:
            tree[()].add(normalized_head)

        lowered = raw_line.lower()
        if command_lower not in lowered:
            continue

        idx = lowered.find(command_lower)
        tail = raw_line[idx + len(command_name):]
        prefix: list[str] = []
        for part in tail.replace("/", " ").split():
            normalized = _normalize_help_token(part, command_lower)
            if not normalized:
                continue
            tree[tuple(prefix)].add(normalized)
            prefix.append(normalized)

    return tree


def _collect_external_help_output(resolved_executable: str, working_dir: str) -> str:
    env = _build_help_environment()

    for switch in EXTERNAL_HELP_SWITCHES:
        args = [resolved_executable]
        if switch:
            args.append(switch)
        try:
            result = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=working_dir,
                env=env,
                text=True,
                errors="replace",
                timeout=EXTERNAL_HELP_TIMEOUT,
            )
        except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError):
            continue

        output = (result.stdout or "") + "\n" + (result.stderr or "")
        if output.strip():
            return output

    return ""


def _parse_candidate_words(
    output: str, command_lower: str, ignore_tokens: set[str]
) -> set[str]:
    if not output:
        return set()

    tokens: set[str] = set()

    def add_candidate(raw: str) -> None:
        raw = raw.strip()
        if not raw:
            return
        normalized = _normalize_help_token(raw, command_lower)
        if not normalized:
            return
        lower = normalized.lower()
        if lower in ignore_tokens or lower in EXTERNAL_STOP_WORDS:
            return
        tokens.add(normalized)

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        for bracket in re.findall(r"\[([^\]]+)\]", line):
            for part in re.split(r"[|,]", bracket):
                add_candidate(part)

        for angle in re.findall(r"<([^>]+)>", line):
            for part in re.split(r"[|,]", angle):
                add_candidate(part)

        for brace in re.findall(r"\{([^}]+)\}", line):
            for part in re.split(r"[|,]", brace):
                add_candidate(part)

        dash_match = re.match(r"([A-Za-z0-9._-]+)\s+-\s+", line)
        if dash_match:
            add_candidate(dash_match.group(1))

        if ":=" in line:
            rhs = line.split(":=", 1)[1]
            for part in rhs.split():
                add_candidate(part)

        if len(tokens) >= 256:
            break

    return tokens


def _collect_external_prefix_output(
    resolved_executable: str, prefix: tuple[str, ...], working_dir: str
) -> set[str]:
    env = _build_help_environment()
    command_lower = os.path.basename(resolved_executable).lower()
    ignore_tokens = {command_lower, *{tok.lower() for tok in prefix}}

    for suffix in EXTERNAL_CONTEXT_SWITCHES:
        args = [resolved_executable, *prefix, *suffix]
        try:
            result = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=working_dir,
                env=env,
                text=True,
                errors="replace",
                timeout=EXTERNAL_HELP_TIMEOUT,
            )
        except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError):
            continue

        output = (result.stdout or "") + "\n" + (result.stderr or "")
        tokens = _parse_candidate_words(output, command_lower, ignore_tokens)
        if tokens:
            return tokens

    return set()


def _ensure_external_prefix_metadata(
    resolved_executable: str, prefix: tuple[str, ...], working_dir: str
) -> tuple[str, ...]:
    tree = EXTERNAL_POSITIONAL_TREE.setdefault(resolved_executable, {})
    if prefix in tree:
        return tree[prefix]

    attempted = EXTERNAL_PREFIX_ATTEMPTED.setdefault(resolved_executable, set())
    if prefix in attempted:
        return tree.get(prefix, ())
    attempted.add(prefix)

    candidates = _collect_external_prefix_output(resolved_executable, prefix, working_dir)
    sorted_candidates = tuple(sorted(candidates)) if candidates else ()
    tree[prefix] = sorted_candidates
    return sorted_candidates


def _ensure_external_metadata(resolved_executable: str, working_dir: str) -> None:
    if (
        resolved_executable in EXTERNAL_FLAG_CACHE
        and resolved_executable in EXTERNAL_POSITIONAL_CACHE
        and resolved_executable in EXTERNAL_POSITIONAL_TREE
    ):
        return

    if resolved_executable in EXTERNAL_METADATA_ATTEMPTED:
        EXTERNAL_FLAG_CACHE.setdefault(resolved_executable, ())
        EXTERNAL_POSITIONAL_CACHE.setdefault(resolved_executable, ())
        EXTERNAL_POSITIONAL_TREE.setdefault(resolved_executable, {})
        return

    output = _collect_external_help_output(resolved_executable, working_dir)
    EXTERNAL_METADATA_ATTEMPTED.add(resolved_executable)

    if not output:
        EXTERNAL_FLAG_CACHE.setdefault(resolved_executable, ())
        EXTERNAL_POSITIONAL_CACHE.setdefault(resolved_executable, ())
        EXTERNAL_POSITIONAL_TREE.setdefault(resolved_executable, {})
        return

    command_name = os.path.basename(resolved_executable)
    flags = tuple(sorted(_extract_flags_from_text(output)))
    positional_tokens = _extract_positionals_from_text(output, command_name)
    tree_sets = _build_positional_tree(output, command_name)
    positional_tokens.update(tree_sets.get((), set()))
    positionals = tuple(sorted(positional_tokens))
    EXTERNAL_FLAG_CACHE[resolved_executable] = flags
    EXTERNAL_POSITIONAL_CACHE[resolved_executable] = positionals
    EXTERNAL_POSITIONAL_TREE[resolved_executable] = {
        prefix: tuple(sorted(values)) for prefix, values in tree_sets.items()
    }


def _get_external_metadata(
    resolved_executable: str, working_dir: str
) -> tuple[tuple[str, ...], tuple[str, ...], dict[tuple[str, ...], tuple[str, ...]]]:
    _ensure_external_metadata(resolved_executable, working_dir)
    return (
        EXTERNAL_FLAG_CACHE.get(resolved_executable, ()),
        EXTERNAL_POSITIONAL_CACHE.get(resolved_executable, ()),
        EXTERNAL_POSITIONAL_TREE.get(resolved_executable, {}),
    )


def _is_flag_context(fragment: str, tokens_before: list[str], spec: CommandSpec) -> bool:
    if not spec.flags:
        return False
    if "--" in tokens_before[1:]:
        return False
    return fragment.startswith("-")


def _collect_used_flags(tokens_before: list[str], spec: CommandSpec) -> set[str]:
    collected: set[str] = set()
    for token in tokens_before:
        if token == "--":
            break
        if token in spec.flags:
            collected.add(token)
    return collected


def complete_first_token(fragment: str, working_dir: str) -> list[str]:
    if _looks_like_path(fragment):
        return complete_path(fragment, working_dir)

    prefix = fragment or ""
    candidates: list[str] = []

    for alias in ALL_COMMAND_ALIASES:
        if alias.startswith(prefix):
            candidates.append(alias)

    if prefix:
        for executable in PATH_EXECUTABLES:
            if executable.startswith(prefix):
                candidates.append(executable)

    ordered = _unique_preserving_order(candidates)
    return ordered


def complete_after_command(fragment: str, tokens_before: list[str], working_dir: str) -> list[str]:
    cmd = tokens_before[0]
    spec = COMMAND_BY_ALIAS.get(cmd)

    if spec is None:
        return complete_external_command(cmd, fragment, tokens_before, working_dir)

    if _is_flag_context(fragment, tokens_before, spec):
        used_flags = _collect_used_flags(tokens_before[1:], spec)
        return [flag for flag in spec.flags if flag.startswith(fragment) and flag not in used_flags]

    if spec.takes_path:
        return complete_path(fragment, working_dir)

    return []


def complete_external_command(cmd: str, fragment: str, tokens_before: list[str], working_dir: str) -> list[str]:
    resolved = resolve_external_executable(cmd, working_dir)
    if not resolved:
        return complete_path(fragment, working_dir)

    if "--" in tokens_before[1:]:
        return complete_path(fragment, working_dir)

    fragment = fragment or ""

    if fragment.startswith("-"):
        flags, _, _ = _get_external_metadata(resolved, working_dir)
        return [flag for flag in flags if flag.startswith(fragment)]

    if _looks_like_path(fragment):
        return complete_path(fragment, working_dir)

    _, base_positionals, tree = _get_external_metadata(resolved, working_dir)

    non_flag_tokens = [tok for tok in tokens_before[1:] if not tok.startswith("-")]
    prefix_tuple = tuple(non_flag_tokens)

    candidates = tree.get(prefix_tuple)
    if candidates is None:
        candidates = _ensure_external_prefix_metadata(resolved, prefix_tuple, working_dir)
        tree = EXTERNAL_POSITIONAL_TREE.get(resolved, {})
        if not candidates:
            candidates = tree.get(prefix_tuple)

    if not candidates and prefix_tuple:
        for i in range(len(prefix_tuple) - 1, -1, -1):
            parent = prefix_tuple[:i]
            parent_candidates = tree.get(parent)
            if parent_candidates is None:
                parent_candidates = _ensure_external_prefix_metadata(resolved, parent, working_dir)
                tree = EXTERNAL_POSITIONAL_TREE.get(resolved, {})
            if parent_candidates:
                candidates = parent_candidates
                break

    if not candidates:
        candidates = base_positionals

    if candidates:
        filtered = [candidate for candidate in candidates if candidate.startswith(fragment)]
        if filtered:
            return filtered

    return complete_path(fragment, working_dir)


def completer(text, state):
    buffer = readline.get_line_buffer()
    beg = readline.get_begidx()
    working_dir = get_current_working_folder() or os.getcwd()

    try:
        tokens_before = _split_tokens(buffer[:beg])
        fragment = text or ""

        if not tokens_before:
            options = complete_first_token(fragment, working_dir)
        else:
            options = complete_after_command(fragment, tokens_before, working_dir)
    except Exception:
        options = []

    if state < len(options):
        return options[state]
    return None


def resolve_external_executable(command: str, working_dir: str) -> str | None:
    expanded = os.path.expanduser(os.path.expandvars(command))
    if "/" in command:
        if os.path.isabs(expanded):
            candidate = os.path.normpath(expanded)
        else:
            candidate = os.path.normpath(os.path.join(working_dir, expanded))
        if os.path.exists(candidate):
            return candidate
        return None
    return shutil.which(expanded)
