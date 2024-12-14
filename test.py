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

project_root = os.path.abspath(os.path.dirname(__file__))
lpsolve_dir = os.path.join(project_root, "lpsolve")

# Check if the required files exist
if not os.path.exists(os.path.join(lpsolve_dir, "lp_lib.h")):
    print("Error: lp_lib.h not found in lpsolve directory.")
    sys.exit(1)

if not any(fname.startswith("lpsolve55") for fname in os.listdir(lpsolve_dir)):
    print("Error: lpsolve55 library not found in lpsolve directory.")
    sys.exit(1)

print(lpsolve_dir)