import os

project_root = os.path.abspath(r'D:\TA\Test Terakhir\clara-master\lpsolve')
test = r'D:\TA\Test Terakhir\clara-master\lpsolve'
test1 = os.path.dirname(os.path.abspath(__file__))
test2 = os.path.join(__file__, 'lpsolve')
test3 = os.path.abspath(__file__)
test4 = os.path.dirname(__file__)
test5 = os.path.abspath(test4+"\\lpsolve")
test6 = os.path.abspath(os.path.join(test4, "lpsolve"))

testEnv = os.getenv("MY_VARIABLE")

print([project_root])
print([test])
print([test1+"\\lpsolve"])
print([test2])
print([test3])
print([test4])
print([test5])
print([test6])
print( test3 == test )
print(testEnv)
