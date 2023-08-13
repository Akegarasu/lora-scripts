import logging


log = logging.getLogger('sd-trainer')


def setup_logging():
    log.setLevel(
        logging.DEBUG
    )
    try:
        import rich

    except ModuleNotFoundError:
        return

    from rich.console import Console
    from rich.logging import RichHandler
    from rich.pretty import install as pretty_install
    from rich.theme import Theme
    from rich.traceback import install as traceback_install

    console = Console(
        log_time=True,
        log_time_format='%H:%M:%S-%f',
        theme=Theme(
            {
                'traceback.border': 'black',
                'traceback.border.syntax_error': 'black',
                'inspect.value.border': 'black',
            }
        ),
    )
    pretty_install(console=console)
    traceback_install(
        console=console,
        extra_lines=1,
        width=console.width,
        word_wrap=False,
        indent_guides=False,
        suppress=[],
    )
    rh = RichHandler(
        show_time=True,
        omit_repeated_times=False,
        show_level=True,
        show_path=False,
        markup=False,
        rich_tracebacks=True,
        log_time_format='%H:%M:%S-%f',
        level=logging.INFO,
        console=console,
    )
    rh.set_name(logging.INFO)
    while log.hasHandlers() and len(log.handlers) > 0:
        log.removeHandler(log.handlers[0])
    log.addHandler(rh)
