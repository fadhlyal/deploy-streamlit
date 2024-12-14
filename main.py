import streamlit as st
import os
import glob
from ast import literal_eval

# Import clara components
from clara.matching import Matching
from clara.interpreter import getlanginter
from clara.parser import getlangparser
from clara.repair import Repair
from clara.feedback import Feedback, FeedGen
from clara.feedback_repair import RepairFeedback
from clara.feedback_simple import SimpleFeedback
from clara.feedback_python import PythonFeedback

# Configure Streamlit page
st.set_page_config(
    page_title="Clara Program Analysis",
    page_icon="🔍",
    layout="wide"
)

def load_program(uploaded_file):
    """Helper function to load and parse program from uploaded file"""
    if uploaded_file is None:
        return None, None
    
    try:
        # Read content of uploaded file
        content = uploaded_file.getvalue().decode("utf-8")
        
        # Get file extension to determine language
        file_extension = uploaded_file.name.split('.')[-1]
        
        # Get parser for the language
        parser = getlangparser(file_extension)
        
        # Parse the code
        model = parser.parse_code(content)
        model.name = uploaded_file.name
        
        return model, file_extension
    except Exception as e:
        st.error(f"Error loading program: {str(e)}")
        return None, None

def load_correct_programs(cluster_dir, lang):
    """Load correct programs from clusters directory"""
    correct_programs = []
    try:
        for f in glob.glob(os.path.join(cluster_dir, f"*.{lang}")):
            with open(f, 'r', encoding='utf-8') as file:
                parser = getlangparser(lang)
                model = parser.parse_code(file.read())
                model.name = f
                correct_programs.append(model)
    except Exception as e:
        st.error(f"Error loading cluster programs: {str(e)}")
    return correct_programs

def main():
    try:
        st.title("Clara Program Analysis")
        
        # Sidebar for analysis type selection
        analysis_type = st.sidebar.radio(
            "Select Analysis Type",
            ["Match", "Repair", "Feedback"]
        )
        
        # Common configuration in sidebar
        st.sidebar.subheader("Configuration")
        verbose = st.sidebar.checkbox("Verbose Output", value=False)
        entry_func = st.sidebar.text_input("Entry Function", value="main")
        timeout = st.sidebar.number_input("Timeout (seconds)", value=60, min_value=1)
        
        # Common input options in sidebar
        st.sidebar.subheader("Program Inputs")
        args_input = st.sidebar.text_area("Arguments (Python list)", help="e.g., [1, 2, 3]")
        ins_input = st.sidebar.text_area("Inputs (Python list)", help="e.g., ['input1', 'input2']")

        # Parse args and ins
        args = None
        ins = None
        try:
            if args_input.strip():
                args = literal_eval(args_input)
            if ins_input.strip():
                ins = literal_eval(ins_input)
        except Exception as e:
            st.error(f"Error parsing arguments or inputs: {str(e)}")
            return

        if analysis_type == "Match":
            st.header("Program Matching")
            
            col1, col2 = st.columns(2)
            with col1:
                program1 = st.file_uploader("Upload first program", key="prog1")
                if program1:
                    st.code(program1.getvalue().decode("utf-8"), language="python")
            with col2:
                program2 = st.file_uploader("Upload second program", key="prog2")
                if program2:
                    st.code(program2.getvalue().decode("utf-8"), language="python")
            
            # Match-specific options
            ignore_io = st.checkbox("Ignore IO", value=False)
            ignore_ret = st.checkbox("Ignore Return Value", value=False)
            bijective = st.checkbox("Bijective Matching", value=True)
            
            if st.button("Match Programs", type="primary"):
                if not (program1 and program2):
                    st.error("Please upload both programs.")
                    return
                
                model1, lang1 = load_program(program1)
                model2, lang2 = load_program(program2)
                
                if lang1 != lang2:
                    st.error("Programs must be in the same language!")
                    return
                
                interpreter = getlanginter(lang1)
                matcher = Matching(
                    ignoreio=ignore_io,
                    ignoreret=ignore_ret,
                    verbose=verbose,
                    bijective=bijective
                )
                
                with st.spinner("Matching programs..."):
                    match_result = matcher.match_programs(
                        model1, model2, interpreter,
                        ins=ins, args=args,
                        entryfnc=entry_func
                    )
                
                if match_result:
                    st.success("Match found!")
                    if verbose:
                        st.json(match_result[1])
                else:
                    st.warning("No match found!")

        else:  # Repair or Feedback
            st.header(f"Program {analysis_type}")
            
            # Upload incorrect program
            incorrect_program = st.file_uploader("Upload program to analyze", key="prog")
            if incorrect_program:
                st.code(incorrect_program.getvalue().decode("utf-8"), language="python")
            
            # Cluster directory input
            cluster_dir = st.text_input("Cluster Directory", value="clusters/test")
            
            if analysis_type == "Repair":
                # Repair-specific options
                clean_strings = st.checkbox("Clean Strings", value=False)
                suboptimal = st.checkbox("Allow Suboptimal Repairs", value=True)
                ignore_io = st.checkbox("Ignore IO", value=False)
                ignore_ret = st.checkbox("Ignore Return Value", value=False)
                
                if st.button("Repair Program", type="primary"):
                    if not incorrect_program:
                        st.error("Please upload a program to repair.")
                        return
                    
                    model, lang = load_program(incorrect_program)
                    if not model:
                        return
                    
                    # Load correct programs from cluster
                    correct_programs = load_correct_programs(cluster_dir, lang)
                    if not correct_programs:
                        st.error(f"No correct programs found in {cluster_dir}")
                        return
                    
                    interpreter = getlanginter(lang)
                    repair = Repair(
                        timeout=timeout,
                        verbose=verbose,
                        allowsuboptimal=suboptimal,
                        cleanstrings=clean_strings
                    )
                    
                    st.info(f"Attempting repairs against {len(correct_programs)} correct program(s)...")
                    
                    for correct_model in correct_programs:
                        with st.spinner(f"Attempting repair using {os.path.basename(correct_model.name)}..."):
                            try:
                                result = repair.repair(
                                    model, correct_model, interpreter,
                                    ins=ins, args=args,
                                    ignoreio=ignore_io,
                                    ignoreret=ignore_ret,
                                    entryfnc=entry_func
                                )
                                
                                if result:
                                    st.success(f"Repair found using {os.path.basename(correct_model.name)}!")
                                    txt = RepairFeedback(model, correct_model, result)
                                    txt.genfeedback()
                                    st.subheader("Suggested Repairs:")
                                    for feedback in txt.feedback:
                                        st.markdown(f"* {feedback}")
                                    break
                            except Exception as e:
                                st.error(f"Error during repair: {str(e)}")
                                if verbose:
                                    st.exception(e)
                    else:
                        st.warning("No repairs found with any correct program.")
                        
            else:  # Feedback
                # Feedback-specific options
                feedback_type = st.selectbox(
                    "Feedback Type",
                    ["repair", "simple", "python"],
                    format_func=lambda x: x.capitalize()
                )
                max_cost = st.number_input("Maximum Feedback Cost", value=0, min_value=0,
                                         help="0 means no limit")
                clean_strings = st.checkbox("Clean Strings", value=False)
                ignore_io = st.checkbox("Ignore IO", value=False)
                ignore_ret = st.checkbox("Ignore Return Value", value=False)
                
                if st.button("Generate Feedback", type="primary"):
                    if not incorrect_program:
                        st.error("Please upload a program for feedback.")
                        return
                    
                    model, lang = load_program(incorrect_program)
                    if not model:
                        return
                    
                    # Load correct programs from cluster
                    correct_programs = load_correct_programs(cluster_dir, lang)
                    if not correct_programs:
                        st.error(f"No correct programs found in {cluster_dir}")
                        return
                    
                    interpreter = getlanginter(lang)
                    
                    # Set feedback module
                    if feedback_type == "repair":
                        feedmod = RepairFeedback
                    elif feedback_type == "python":
                        feedmod = PythonFeedback
                    else:
                        feedmod = SimpleFeedback
                    
                    feedgen = FeedGen(
                        verbose=verbose,
                        timeout=timeout,
                        allowsuboptimal=True,
                        feedmod=feedmod
                    )
                    
                    with st.spinner("Generating feedback..."):
                        try:
                            feedback = feedgen.generate(
                                model, correct_programs, interpreter,
                                ins=ins, args=args,
                                ignoreio=ignore_io,
                                ignoreret=ignore_ret,
                                cleanstrings=clean_strings,
                                entryfnc=entry_func
                            )
                            
                            if feedback.status == Feedback.STATUS_REPAIRED:
                                if max_cost > 0 and feedback.cost > max_cost:
                                    st.error(f'Max cost exceeded ({feedback.cost} > {max_cost})')
                                else:
                                    st.success("Feedback generated successfully!")
                                    st.subheader("Feedback:")
                                    for f in feedback.feedback:
                                        st.markdown(f"* {f}")
                            elif feedback.status == Feedback.STATUS_ERROR:
                                st.error(f"Error generating feedback: {feedback.error}")
                            else:
                                st.warning(feedback.statusstr())
                                
                        except Exception as e:
                            st.error(f"Error generating feedback: {str(e)}")
                            if verbose:
                                st.exception(e)

    except Exception as e:
        st.error(f"An unexpected error occurred: {str(e)}")
        if verbose:
            st.exception(e)

if __name__ == "__main__":
    main()
