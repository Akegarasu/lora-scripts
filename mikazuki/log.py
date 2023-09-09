import logging


log = logging.getLogger('sd-trainer')
log.setLevel(logging.DEBUG)

try:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.pretty import install as pretty_install
    from rich.theme import Theme

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

except ModuleNotFoundError:
    pass

