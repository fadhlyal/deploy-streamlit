import pytest

from utils import get_full_data_filename, parse_file

from clara.interpreter import getlanginter
from clara.matching import Matching
from clara.parser import getlangparser


## Matching helper functions:

def matching_helper(f1, f2, lang, ins=None, args=None, entryfnc="main",
                    datadir="data"):
    f1 = get_full_data_filename(f1, reldir=datadir)
    f2 = get_full_data_filename(f2, reldir=datadir)
    
    parser = getlangparser(lang)
    inter = getlanginter(lang)

    m1 = parse_file(f1, parser)
    m2 = parse_file(f2, parser)

    M = Matching(ignoreio=not ins, ignoreret=not args)
    return not not M.match_programs(m1, m2, inter, ins=ins,
                                    args=args, entryfnc=entryfnc)

def matching_test_helper(f1, f2, lang, should_match, *args, **kwargs):
    m1 = matching_helper(f1, f2, lang, *args, **kwargs)
    assert m1 == should_match

    # If f1 (not) matches f2, then f2 should also (not) match f1
    m2 = matching_helper(f2, f1, lang, *args, **kwargs)
    assert m2 == should_match

    
## C matching tests:
    
testdata_c = [
    ('p1.c', 'p2.c', [[4]], True),
    ('sym1.c', 'sym2.c', [[3]], False),
    ('continue.c', 'continue.c', [[]], True),
    ('arrayFun.c', 'arrayFun.c', [[]], True),
]

@pytest.mark.parametrize(
    ('f1', 'f2', 'ins', 'should_match'),
    testdata_c)
def test_match_c(f1, f2, ins, should_match):
    """
    Tests whether the C files `f1` and `f2` match with the inputs `ins`.
    `should_match` indicates whether the files should match.
    """
    matching_test_helper(f1, f2, 'c', should_match, ins=ins)


## Python matching tests:

def test_examples():
    args=[[[4.5]], [[1.0,3.0,5.5]]]
    matching_test_helper('c1.py', 'c2.py', 'py', True, args=args,
                         datadir="../examples", entryfnc="computeDeriv")
    matching_test_helper('c1.py', 'c3.py', 'py', False, args=args,
                         datadir="../examples", entryfnc="computeDeriv")
    matching_test_helper('c2.py', 'c3.py', 'py', False, args=args,
                         datadir="../examples", entryfnc="computeDeriv")
    
