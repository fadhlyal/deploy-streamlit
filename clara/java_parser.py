'''
JAVA parser
'''

# clara lib imports
from .parser import Parser, ParseError, addlangparser, NotSupported, ParseError

class JavaParser(Parser):

    def __init__(self, *args, **kwargs):
        super(JavaParser, self).__init__(*args, **kwargs)

    def parse(self, code):
        """
        Parses JAVA code
        """

        # TODO
        raise NotImplementedError("Not yet implemented")

# Register JAVA parser
addlangparser('java', JavaParser)
