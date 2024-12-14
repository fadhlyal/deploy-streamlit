"""
JAVA interpreter
"""

# clara lib imports
from .interpreter import Interpreter, addlanginter, RuntimeErr, UndefValue

class JavaInterpreter(Interpreter):

    # TODO
    pass

# Register JAVA interpreter
addlanginter('java', JavaInterpreter)
