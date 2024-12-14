'''
Generating textual feedback from repair for Python programs
'''

from .model import Op, Var, Const, VAR_COND, VAR_RET, VAR_OUT

PRIMITIVE_FUNC = ['len']

BINARY_OPS = {
    'And': 'and',
    'Or': 'or',
    'Add': '+',
    'AssAdd': '+',
    'Sub': '-',
    'Mult': '*',
    'Div': '/',
    'Mod': '%',
    'Pow': '**',
    'LShift': '<<',
    'RShift': '>>',
    'BitOr': '|',
    'BitAnd': '&',
    'BitXor': '^',
    'FloorDiv': '//',
    'Eq':'==',
    'NotEq':'!=',
    'Lt':'<',
    'LtE':'<=',
    'Gt':'>',
    'GtE':'>=',
    'Is':'is',
    'IsNot':'is not',
    'In':'in',
    'NotIn':'not in'
}
UNARY_OPS = {
    'Invert': '~',
    'Not': 'not ',
    'UAdd': '+',
    'USub': '-'
}


class PythonFeedback(object):

    def __init__(self, impl, spec, result, cleanstrings=None):
        self.impl = impl
        self.spec = spec
        self.result = result
        self.feedback = []

        self.expr_orig = None

    def add(self, msg, *args):
        if args:
            msg %= args
        if self.expr_orig:
            msg = '%s [%s]' % (msg, self.expr_orig)
        self.feedback.append('* ' + msg)

    def genfeedback(self):
        gen = PythonStatementGenerator()
        # Iterate all functions
        # fname - function name
        # mapping - one-to-one mapping of variables
        # repairs - list of repairs
        # sm - structural matching betweeb locations of programs
        for fname, (mapping, repairs, sm) in list(self.result.items()):

            # Copy mapping with converting '*' into a 'new_' variable
            nmapping = {k: '$new_%s' % (k,)
                        if v == '*' else v for (k, v) in list(mapping.items())}

            # Go through all repairs
            # loc1 - location from the spec.
            # var1 - variable from the spec.
            # var2 - variable from the impl.
            # cost - cost of the repair
            for rep in repairs:

                loc1 = rep.loc1
                var1 = rep.var1
                var2 = rep.var2
                cost = rep.cost
                expr1 = rep.expr1
                self.expr_orig = rep.expr1_orig

                # Get functions and loc2
                fnc1 = self.spec.getfnc(fname)
                fnc2 = self.impl.getfnc(fname)
                loc2 = sm[loc1]

                # Get exprs (spec. and impl.)
                #expr1 = fnc1.getexpr(loc1, var1)
                expr2 = fnc2.getexpr(loc2, var2)

                # Location of the expression
                if expr2.line:
                    # Either line
                    locdesc = 'at %s' % (expr2.line,)
                else:
                    # Or location description
                    locdesc = fnc2.getlocdesc(loc2)

                # Delete feedback
                if var1 == '-':
                    self.add("Delete '%s' at line %s (cost=%s)",
                             str(gen.assignmentStatement(var2, expr2)), expr2.line, cost)
                    continue

                # Rewrite expr1 (from spec.) with variables of impl.
                expr1 = expr1.replace_vars(nmapping)

                # '*' means adding a new variable (and also statement)
                if var2 == '*':
                    self.add("Add assignment '%s' %s (cost=%s)",
                             str(gen.assignmentStatement('$new_%s' % (var1,), expr1)), locdesc, cost)
                    continue

                # Output original and new (rewriten) expression for var2
                
                if var2.startswith('iter#'):
                    pyexpr1 = gen.pythonExpression(expr1, True)[0]
                    pyexpr2 = gen.pythonExpression(expr2, True)[0]
                    self.add("Change iterated expression of for loop '%s' to '%s' %s (cost=%s)", str(pyexpr2), str(pyexpr1), locdesc, cost)
                elif str(var2) == str(expr2):
                    self.add("Add a statement '%s' %s (cost=%s)", str(gen.assignmentStatement(var2, expr1)), locdesc, cost)
                else:
                    self.add(
                        "Change '%s' to '%s' %s (cost=%s)",
                        str(gen.assignmentStatement(var2, expr2)), str(gen.assignmentStatement(var2, expr1)), locdesc, cost)
                
                
class PythonStatementGenerator(object):
    def __init__(self):
        self.indexVariables = {}
        self.indentation = 0
        
    def assignmentStatement(self, var, expr, replacement=None):
        try:
            if var == VAR_COND:
                return self.pythonExpression(expr, replacement)[0]
            elif var == VAR_RET:
                return PyReturn(self.pythonExpression(expr, replacement)[0])
            elif var == VAR_OUT:
                return PyPrint(self.pythonExpression(expr, replacement)[0])
            try:
                if expr.name == 'GetElement' and expr.args[0].name.startswith('iter#') and expr.args[1].name.startswith('ind#'):
                    self.indexVariables[(expr.args[0].name, expr.args[1].name)] = var
            except NameError:
                pass
            except AttributeError:
                pass
            return self.generateAssignments(var, expr, replacement)
        except NotAnLValueException as ex:
            if expr.name == 'ite':
                return self.pythonIfThenElseClause(var, expr, replacement)
            else:
                raise
    
    def generateAssignments(self, var, expr, replacement=None): # unmerge any wrongly merged things
        pyexpr = self.pythonExpression(expr, replacement)
        assignment = PyAssignment(PyVariable(var), pyexpr[0])
        try:
            if self.shouldEliminateLeftSide(expr):
                assignment = pyexpr[0]
            if str(assignment.assigned.elseexpr) == str(var): # if we have an 'ite' with an else part that's supposed to be empty
                assignment.assigned.elseexpr = None
        except AttributeError:
            pass
        return self.extractAssignments(pyexpr[1], assignment)
        
    def shouldEliminateLeftSide(self, expr):
        return expr.name == 'AssignElement' or expr.name == 'Delete' or (expr.name == 'ite' and self.shouldEliminateLeftSide(expr.args[1]))
        
    def areExpressionsEqual(self, expr1, expr2):
        try:
            if expr1.name != expr2.name:
                return False
            return expr1.args == expr2.args
        except TypeError:
            return False
        
    def getBoundVarName(self, bvarnumber): # should return x, y, z, x1, y1, z1, x2, y2, ...
        if bvarnumber/3 == 0:
            bvarname = str(chr(120+bvarnumber%3))
        else:
            bvarname = str(chr(120+bvarnumber%3)) + str(bvarnumber/3)
        return bvarname

    def pythonIfThenElseClause(self, var, expr, replacement):
        ret = []
        if expr.name == 'ite':
            ret = ret + [(PyCondition(self.pythonExpression(expr.args[0])[0]), self.indentation)]
            self.indentation = self.indentation + 1
            try:
                ret = ret + [(self.assignmentStatement(var, expr.args[1]), self.indentation, replacement)]
            except NotAnLValueException as ex:
                ret = ret + [(PyAssignment(PyVariable(var), self.pythonExpression(ex.orig_val)[0]), self.indentation)]
                if replacement == None:
                    replacement = []
                ret = ret + [(self.assignmentStatement(var, expr.args[1], replacement + [(ex.orig_val, var)]), self.indentation)]
            self.indentation = self.indentation - 1
            ret = ret + [('else', self.indentation)]
            self.indentation = self.indentation + 1
            try:
                ret = ret + [(self.assignmentStatement(var, expr.args[2]), self.indentation, replacement)]
            except NotAnLValueException as ex:
                ret = ret + [(PyAssignment(PyVariable(var), self.pythonExpression(ex.orig_val)[0]), self.indentation, replacement)]
                if replacement == None:
                    replacement = []
                ret = ret + [(self.assignmentStatement(var, expr.args[2], replacement + [(ex.orig_val, var)]), self.indentation)]
            self.indentation = self.indentation - 1
        return PyIfThenElseClause(ret)

    def pythonExpression(self, expr, replacement=None):
        assignments = []
        ret = None
        if replacement:
            try:
                for repl in replacement:
                    if self.areExpressionsEqual(expr, repl[0]):
                        ret = PyVariable(repl[1])
                    for arg, i in expr.args:
                        if self.areExpressionsEqual(arg, repl[0]):
                            expr.args[i] = PyVariable(repl[1])
            except TypeError:
                pass
            except AttributeError:
                pass
        if ret == None:
            try:
                args_both = [self.pythonExpression(arg, replacement) for arg in expr.args]
                args = []
                for arg in args_both:
                    args.append(arg[0])
                    assignments = assignments + arg[1]
                if expr.name == 'ListInit':
                    ret = PyListInit(args)
                elif expr.name == 'SetInit':
                    ret = PySetInit(args)
                elif expr.name == 'DictInit':
                    ret = PyDictInit(args)
                elif expr.name == 'TupleInit':
                    ret = PyTupleInit(args)
                elif expr.name == 'AssignElement':
                    try:
                        ret = PyAssignment(PyGetElement(args[0], args[1]), args[2])
                    except NotAnLValueException as ex:
                        ex.orig_val = expr.args[0]
                        raise ex
                elif expr.name in BINARY_OPS:
                    ret = PyBinaryOperation(args[0], expr.name, args[1])
                elif expr.name in UNARY_OPS:
                    ret = PyUnaryOperation(expr.name, args[0])
                elif expr.name == 'StrAppend':
                    ret = PyStrAppend(args[0], args[1])
                elif expr.name == 'ite':
                    ret = PyIfThenElse(args[0], args[1], args[2])
                elif expr.name == 'GetAttr':
                    ret = PyGetAttr(args[0], args[1])
                elif expr.name == 'Slice':
                    ret = PySlice(args[0], args[1], args[2])
                elif expr.name == 'GetElement':
                    try:
                        if (args[0].name, args[1].name) in self.indexVariables:
                            ret = PyVariable(self.indexVariables[args[0].name, args[1].name])
                        else:
                            ret = PyGetElement(args[0], args[1])
                    except AttributeError:
                        try:
                            if (expr.args[0].name) == 'pop':
                                if str(expr.args[1]) == '0':
                                    ret = PyFuncCall('pop#list', [])
                                elif str(expr.args[1]) == '1':
                                    ret = PyFuncCall('pop#element', [])
                                else:
                                    ret = PyGetElement(args[0], args[1])
                        except AttributeError:
                            ret = PyGetElement(args[0], args[1])
                    ret = PyGetElement(args[0], args[1])
                elif expr.name == 'Delete':
                    ret = PyDelete(args)
                elif expr.name == 'FuncCall':
                    ret = PyFuncCall(args[0], (args[1:]))
                elif expr.name == 'ListComp':
                    ret = PyListComp(args[1], [PyComprehension([PyVariable(self.getBoundVarName(x)) for x in range(int(str(args[0])))], args[-2], [args[-1]])])
                elif expr.name == 'SetComp':
                    ret = PySetComp(args[1], [PyComprehension([PyVariable(self.getBoundVarName(x)) for x in range(int(str(args[0])))], args[-2], [args[-1]])])
                elif expr.name == 'DictComp':
                    ret = PyDictComp(args[1], args[2], [PyComprehension([PyVariable(self.getBoundVarName(x)) for x in range(int(str(args[0])))], args[-2], [args[-1]])])
                elif expr.name == 'GeneratorExp':
                    ret = PyGeneratorExp(args[1], [PyComprehension([PyVariable(self.getBoundVarName(x)) for x in range(int(str(args[0])))], args[-2], [args[-1]])])
                elif expr.name == 'BoundVar':
                    ret = PyVariable(self.getBoundVarName(int(expr.args[0].value)))
                elif expr.args != None:
                    try:
                        if expr.name in PRIMITIVE_FUNC or callable(eval(expr.name)):
                            ret = PyFuncCall(expr.name, args)
                        else:
                            ret = PyFuncCall(PyGetAttr(self.pythonExpression(expr.args[0])[0], expr.name), args[1:])
                    except NameError:
                        ret = PyFuncCall(PyGetAttr(self.pythonExpression(expr.args[0])[0], expr.name), args[1:])
            except AttributeError as ex:
                try:
                    ret = PyConstant(expr.value)
                except AttributeError:
                    ret = PyVariable(expr.name)
            else:
                pass
        if expr.original:
            var_ret = PyVariable(expr.original[0])
            assignments.append((var_ret, ret, expr.original[1]))
            ret = var_ret
        previous_ids = []
        ret_assignments = []
        for i in range(len(assignments)): # eliminate duplicates
            if assignments[i][2] not in previous_ids:
                ret_assignments.append(assignments[i])
                previous_ids.append(assignments[i][2])
        return [ret, ret_assignments]

    def extractAssignments(self, assignmentlist, assignment):
        ret_assignmentlist = []

        if len(assignmentlist) > 0:
            for ass in assignmentlist:
                if (str(ass[0]) != str(ass[1]).strip()) and (not str(ass[1]).strip().startswith('iter#')):
                    ret_assignmentlist.append(PyAssignment(ass[0], ass[1]))
            return PyAssignments(ret_assignmentlist+[assignment])
        return assignment
    
class StandaloneStatementException(Exception):
    def __init__(self, value):
        self.value = value
        
    def __str__(self):
        return repr(self.value)
    
class PyStatement(object):
    def __init__(self, value):
        self.value = value
    
    def __repr__(self):
        return self.value

class PyCondition(PyStatement):
    def __init__(self, cond):
        self.cond = cond
        
    def __repr__(self):
        return 'if %s:' % str(self.cond)
    
class PyReturn(PyStatement):
    def __init__(self, arg):
        self.arg = arg
        
    def __repr__(self):
        return 'return %s' % str(self.arg)
    
class PyPrint(PyStatement):
    def __init__(self, arg):
        self.arg = arg
        
    def __repr__(self):
        if(isinstance(self.arg, PyStrAppend)):
            try:
                if self.arg.left.name == VAR_OUT:
                    return 'print %s' % str(self.arg.right)
                elif self.arg.right.name == VAR_OUT:
                    return 'print %s' % str(self.arg.left)
                    
            except AttributeError:
                pass
            return '%s; %s' % (str(PyPrint(self.arg.left)), str(PyPrint(self.arg.right)))
            
        return 'print %s' % str(self.arg)
    
class PyExpression(PyStatement):
    def __init__(self, value):
        self.value = value
    
    def __repr__(self):
        return self.value
    
    def isLValue(self):
        return False
    
class PyLValue(PyExpression):
    def __init__(self, value):
        self.value = value
    
    def __repr__(self):
        return self.value
    
    def isLValue(self):
        return True
    
class PyAssignment(PyExpression):
    def __init__(self, variable, assigned):
        if not variable.isLValue():
            raise NotAnLValueException(variable)
        self.variable = variable
        self.assigned = assigned
        
    def __repr__(self):
        return '%s = %s' % (str(self.variable), str(self.assigned))
    
class NotAnLValueException(Exception):
    def __init__(self, value):
        self.value = value
        
    def __str__(self):
        return repr(self.value)
    
class PyAssignments(PyStatement):
    def __init__(self, assignments):
        self.assignments = assignments
        
    def __repr__(self):
        return '; '.join([str(assignment) for assignment in self.assignments])
    
class PyVariable(PyLValue):
    def __init__(self, name):
        self.name = name
        
    def __repr__(self):
        return self.name

class PyConstant(PyExpression):
    def __init__(self, value):
        self.value = value
        
    def __repr__(self):
        return self.value
    
        
class PyListInit(PyExpression):
    def __init__(self, args):
        self.args = args
    
    def __repr__(self):
        arguments = [str(arg) for arg in self.args]
        return '[%s]' % ','.join(arguments)
        
class PySetInit(PyExpression):
    def __init__(self, args):
        self.args = args
    
    def __repr__(self):
        arguments = [str(arg) for arg in self.args]
        return 'set([%s])' % ', '.join(arguments)
        
class PyDictInit(PyExpression):
    def __init__(self, args):
        self.args = args
    
    def __repr__(self):
        arguments = [str(arg) for arg in self.args]
        return '{%s}' % ', '.join([arguments[i-1]+': '+arguments[i] for i in range(1,len(arguments))])
        
class PyTupleInit(PyExpression):
    def __init__(self, args):
        self.args = args
    
    def __repr__(self):
        arguments = [str(arg) for arg in self.args]
        if len(arguments) == 1:
            return '(%s,)' % arguments[0]
        return '(%s)' % ', '.join(arguments)
    
    
class PyBinaryOperation(PyExpression):
    def __init__(self, left, op, right):
        self.left = left
        self.right = right
        self.op = op
        
    def __repr__(self):
        return '(%s %s %s)' % (str(self.left), BINARY_OPS[self.op], str(self.right))
        

class PyUnaryOperation(PyExpression):
    def __init__(self, op, arg):
        self.op = op
        self.arg = arg
        
    def __repr__(self):
        return '(%s%s)' % (UNARY_OPS[self.op], str(self.arg))
    
class PyStrAppend(PyExpression):
    def __init__(self, left, right):
        self.left = left
        self.right = right
        
    def __repr__(self):
        return '(%s + %s)' % (str(self.left), str(self.right))

class PyIfThenElse(PyExpression):
    def __init__(self, ifexpr, thenexpr, elseexpr):
        self.ifexpr = ifexpr
        self.thenexpr = thenexpr
        self.elseexpr = elseexpr
        
    def __repr__(self):
        if self.elseexpr == None:
            return '(%s if %s)' % (str(self.thenexpr), str(self.ifexpr))
        else:
            return '(%s if %s else %s)' % (str(self.thenexpr), str(self.ifexpr), str(self.elseexpr))
    
class PyGetAttr(PyLValue):
    def __init__(self, obj, attr):
        self.obj = obj
        self.attr = attr
    
    def __repr__(self):
        return '%s.%s' % (str(self.obj), str(self.attr))
        
class PySlice(PyExpression):
    def __init__(self, lower, upper, step):
        self.lower = lower
        self.upper = upper
        self.step = step
    
    def __repr__(self):
        ret = ':'
        if str(self.lower) != 'None':
            ret = '%s:' % str(self.lower)
        if str(self.upper) != 'None':
            ret = ret + str(self.upper)
        if str(self.step) != 'None':
            ret = ret + ':' + str(self.step)
            
        return ret
        
class PyGetElement(PyExpression):
    def __init__(self, collection, index):
        self.collection = collection
        self.index = index
    
    def __repr__(self):
        return '%s[%s]' % (str(self.collection), str(self.index))
    
    def isLValue(self):
        return self.collection.isLValue()
        
class PyDelete(PyStatement):
    def __init__(self, args):
        self.args = args
        
    def __repr__(self):
        arguments = [str(arg) for arg in self.args]
        return 'del %s' % ', '.join(arguments)
    
class PyFuncCall(PyExpression):
    def __init__(self, func, args):
        self.func = func
        self.args = args
    
    def __repr__(self):
        arguments = [str(arg) for arg in self.args]
        return '%s(%s)' % (str(self.func), (', ').join(arguments))
    
class PyComprehension(PyExpression):
    def __init__(self, target, iter, ifs):
        self.target = target
        self.iter = iter
        self.ifs = ifs
        
    def __repr__(self):
        ret = 'for %s in %s' % (', '.join([str(var) for var in self.target]), str(self.iter))
        if len(self.ifs) != 1 or str(self.ifs[0]) != 'True':
            ret = ret + ' if ' + 'if '.join([str(cond) for cond in self.ifs])
        return ret
    
class PyListComp(PyExpression):
    def __init__(self, elt, generators):
        self.elt = elt
        self.generators = generators
        
    def __repr__(self):
        return '[%s %s]' % (self.elt , ' '.join([str(gen) for gen in self.generators]))
        
class PySetComp(PyExpression):
    def __init__(self, elt, generators):
        self.elt = elt
        self.generators = generators
        
    def __repr__(self):
        return '{%s %s}' % (self.elt , ' '.join([str(gen) for gen in self.generators]))
        
class PyDictComp(PyExpression):
    def __init__(self, key, value, generators):
        self.key = key
        self.value = value
        self.generators = generators
        
    def __repr__(self):
        return '{%s: %s %s}' % (self.key, self.value, (' ').join([str(gen) for gen in self.generators]) )
    
class PyGeneratorExp(PyExpression):
    def __init__(self, elt, generators):
        self.elt = elt
        self.generators = generators
        
    def __repr__(self):
        return '%s %s' % (self.elt , ' '.join([str(gen) for gen in self.generators]))

class PyIfThenElseClause(PyStatement):
    def __init__(self, value):
        self.value = value
    def __repr__(self):
        ret = '\n'
        for statement in self.value:
            if statement[0] == 'else':
                ret = ret + statement[1]*'\t'+'else:'
            else:
                ret = ret + statement[1]*'\t'+str(statement[0])
            ret = ret + '\n'
        return ret