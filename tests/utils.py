import os

dir_path = os.path.dirname(os.path.realpath(__file__))

def get_full_data_filename(f, reldir='data'):
    """
    Gets the full path to the data file `f`.
    """
    return os.path.join(dir_path, reldir, f)

def parse_file(fname, parser):
    """
    Parses the file `fname` using the parser `parser` and returns the resulting model.
    """
    with open(fname, encoding="utf-8") as f:
        code = f.read()
    model = parser.parse_code(code)
    model.src = fname
    return model
