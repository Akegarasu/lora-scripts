import os
from mikazuki.log import log
try:
    import tkinter
    from tkinter.filedialog import askdirectory, askopenfilename
except ImportError:
    tkinter = None
    askdirectory = None
    askopenfilename = None
    log.warning("tkinter not found, file selector will not work.")

last_dir = ""


def tk_window():
    window = tkinter.Tk()
    window.wm_attributes('-topmost', 1)
    window.withdraw()


def open_file_selector(
        initialdir="",
        title="Select a file",
        filetypes="*") -> str:
    global last_dir
    if last_dir != "":
        initialdir = last_dir
    elif initialdir == "":
        initialdir = os.getcwd()
    try:
        tk_window()
        filename = askopenfilename(
            initialdir=initialdir, title=title,
            filetypes=filetypes
        )
        last_dir = os.path.dirname(filename)
        return filename
    except:
        return ""


def open_directory_selector(initialdir) -> str:
    global last_dir
    if last_dir != "":
        initialdir = last_dir
    elif initialdir == "":
        initialdir = os.getcwd()
    try:
        tk_window()
        directory = askdirectory(
            initialdir=initialdir
        )
        last_dir = directory
        return directory
    except:
        return ""
