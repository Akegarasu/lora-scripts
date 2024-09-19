

_origin_print = print


def i18n_print(data, *args, **kwargs):
    _origin_print(data, *args, **kwargs)
    _origin_print("i18n_print")


__builtins__["print"] = i18n_print
