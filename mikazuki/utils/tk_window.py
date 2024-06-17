from mikazuki.log import log
try:
    import tkinter
    from tkinter.filedialog import askdirectory, askopenfilename
except ImportError:
    tkinter = None
    askdirectory = None
    askopenfilename = None
    log.warning("tkinter not found, file selector will not work.")


def tk_window():
    window = tkinter.Tk()
    window.wm_attributes('-topmost', 1)
    window.withdraw()


def open_file_selector(
        initialdir,
        title,
        filetypes) -> str:
    try:
        tk_window()
        filename = askopenfilename(
            initialdir=initialdir, title=title,
            filetypes=filetypes
        )
        return filename
    except:
        return ""


def open_directory_selector(initialdir) -> str:
    try:
        tk_window()
        directory = askdirectory(
            initialdir=initialdir
        )
        return directory
    except:
        return ""
