import streamlit as st
try:
    st.rerun()
except Exception as e:
    with open("rerun_catch.txt", "w") as f:
        f.write("Caught Exception")
except BaseException as e:
    with open("rerun_catch.txt", "w") as f:
        f.write("Caught BaseException")
