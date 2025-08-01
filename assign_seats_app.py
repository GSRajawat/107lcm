def delete_file_app():
    """
    Streamlit application to delete a specified file (abc.csv).
    """
    st.title("File Deletion App")
    st.write("This app allows you to delete the 'abc.csv' file from the current directory.")

    file_to_delete = "timetable.csv"

    # Check if the file exists
    if os.path.exists(file_to_delete):
        st.info(f"The file '{file_to_delete}' currently exists.")
        if st.button(f"Delete {file_to_delete}"):
            try:
                os.remove(file_to_delete)
                st.success(f"Successfully deleted '{file_to_delete}'.")
            except OSError as e:
                st.error(f"Error: Could not delete '{file_to_delete}'. Reason: {e}")
            # Re-run the app to update the file existence status
            st.experimental_rerun()
    else:
        st.warning(f"The file '{file_to_delete}' does not exist in the current directory.")
        st.info("You might need to create it first for the delete button to appear.")

if __name__ == "__main__":
    delete_file_app()
