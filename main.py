import streamlit as st
import os

my_variable = os.getenv("MY_VARIABLE")
a = r'/workspaces/deploy-streamlit/lpsolve'

st.write("Hello, Streamlit!")
st.write(my_variable)
st.write(a)