from libc.stdio cimport FILE

cdef extern from "lpsolve/lp_lib.h":
  ctypedef struct lprec:
    pass

  cdef int EQ
  cdef int LE
  cdef int GE

  cdef int TIMEOUT
  cdef int SUBOPTIMAL
  cdef int NUMFAILURE

  # Creation/Deletion
  lprec* make_lp(int rows, int cols)
  void delete_lp(lprec* lp)

  # Option setting operations
  void set_timeout(lprec* lp, long secs)
  void set_verbose(lprec* lp, int verbose)
  void set_outputstream(lprec *lp, FILE *stream)
  unsigned char set_add_rowmode(lprec* lp, unsigned char turnon)

  # Model options
  void set_int(lprec* lp, int column, unsigned char must_be_int)
  void set_upbo(lprec* lp, int column, double value)
  void set_presolve(lprec *lp, int do_presolve, int maxloops)
  int get_presolveloops(lprec *lp)
  void set_bb_rule(lprec *lp, int bb_rule)
  void set_scaling(lprec *lp, int scalemode)
  unsigned char set_binary(lprec *lp, int column, unsigned char must_be_bin)

  # Setting/Getting matrix values
  unsigned char add_constraint(lprec* lp, double* row, int ctype, double rh)
  unsigned char add_constraintex(lprec* lp, int count, double* row, int* colno, int ctype, double rh)
  unsigned char set_obj_fnex(lprec* lp, int count, double* row, int* colno)
  unsigned char get_ptr_variables(lprec* lp, double** ptr)
  int get_Ncolumns(lprec *lp)
  unsigned char set_rh(lprec *lp, int row, double value)
  int add_SOS(lprec *lp, char *name, int sostype, int priority, int count, int *sosvars, double *weights)
  
  # Operations on the model
  int solve(lprec* lp)
  
  # Misc/Helper
  void print_lp(lprec* lp)
  void print_solution(lprec* lp, int columns)
