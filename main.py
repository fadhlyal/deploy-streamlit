import streamlit as st
import os

my_variable = os.getenv("MY_VARIABLE")

st.write("Hello, Streamlit!")
st.write(my_variable)