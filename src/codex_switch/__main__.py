import sys

from .bootstrap import build_application
from .domain.errors import SwitchError
from .presentation.cli import CLI
from .presentation.console import Console


def main(args=None):
    arguments = list(sys.argv[1:] if args is None else args)
    if arguments == ["_claude-statusline"]:
        from .infrastructure.providers.statusline import main as statusline
        return statusline()
    try:
        from .infrastructure.processes import prepare_file_limit
        prepare_file_limit()
        from .infrastructure.platforms import current_platform
        return CLI(build_application(), Console(terminal=current_platform().terminal)).run(arguments)
    except SwitchError as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError) as exc:
        print("Не удалось выполнить команду. Проверь установку: runlobby doctor", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
