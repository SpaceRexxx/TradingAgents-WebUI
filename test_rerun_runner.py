import sys
from streamlit.runtime.scriptrunner.script_runner import RerunException
print(issubclass(RerunException, Exception))
