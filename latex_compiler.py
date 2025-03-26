#!/usr/bin/env python3
"""
LaTeX Compiler Module for APOLLO AI
Compiles LaTeX content to PDF files for display in the web app.
"""

import os
import platform
import shutil
import subprocess
import uuid
import glob
from pathlib import Path
from datetime import datetime

def cleanup_temp_latex_files():
    """Clean up orphaned temporary LaTeX files."""
    temp_dir = Path("temp_latex")
    if not temp_dir.exists():
        return
    
    try:
        # Get all directories that start with latex_temp_
        temp_subdirs = [d for d in temp_dir.iterdir() if d.is_dir() and d.name.startswith("latex_temp_")]
        
        # Clean up each directory
        for subdir in temp_subdirs:
            try:
                print(f"Cleaning up temporary directory: {subdir}")
                # Delete all files in the directory
                for file_path in subdir.glob("*"):
                    if file_path.is_file():
                        file_path.unlink()
                
                # Delete the directory itself
                subdir.rmdir()
                print(f"Successfully removed {subdir}")
            except Exception as e:
                print(f"Error cleaning up {subdir}: {e}")
    except Exception as e:
        print(f"Error during temp files cleanup: {e}")
        
    # Also check for stray VSCode temp files
    vscode_temp_pattern = os.path.join(os.path.expanduser('~'), "AppData", "Local", "Programs", "Microsoft VS Code", "latex_temp_*")
    try:
        for temp_dir in glob.glob(vscode_temp_pattern):
            if os.path.isdir(temp_dir):
                try:
                    print(f"Cleaning up VSCode temp directory: {temp_dir}")
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    print(f"Error cleaning up VSCode temp directory {temp_dir}: {e}")
    except Exception as e:
        print(f"Error checking for VSCode temp directories: {e}")

def compile_latex_to_pdf(latex_content, user_id, topic_code, title="OCR A-Level Computer Science Practice Paper"):
    """
    Compiles LaTeX content to PDF and saves it in a user-specific directory.
    Returns the path to the generated PDF, relative to the 'static' directory.
    
    Args:
        latex_content (str): The LaTeX code to compile
        user_id (int): User ID for organizing PDFs by user
        topic_code (str): Topic code for file naming
        title (str, optional): Paper title for file naming
    
    Returns:
        str: Path to the generated PDF relative to 'static' directory, or None if compilation failed
    """
    # Print verbose debugging information
    print(f"Starting LaTeX compilation for user {user_id}, topic {topic_code}")
    print(f"Current working directory: {os.getcwd()}")
    print(f"Platform: {platform.system()} {platform.release()}")
    
    # Sanitize inputs for filenames
    user_id_str = str(user_id)
    topic_code_str = topic_code.replace(".", "_").replace(" ", "")
    
    # Create a base directory for storing PDFs
    pdf_base_dir = Path("static/generated_pdfs")
    pdf_base_dir.mkdir(exist_ok=True)
    
    # Create user-specific directory
    user_dir = pdf_base_dir / user_id_str
    user_dir.mkdir(exist_ok=True)
    
    # Create unique filename based on topic and timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    pdf_filename = f"{topic_code_str}_{timestamp}_{unique_id}.pdf"
    final_pdf_path = user_dir / pdf_filename
    
    # Create a temporary directory for compilation in a consistent location
    temp_dir = Path("temp_latex") / f"latex_temp_{unique_id}"
    temp_dir.mkdir(exist_ok=True, parents=True)
    tex_file_path = temp_dir / "temp.tex"
    print(f"Creating temp directory: {temp_dir}")
    print(f"Temp directory exists: {temp_dir.exists()}")
    
    
    # Store original directory
    original_dir = os.getcwd()
    
    try:
        # Process LaTeX content to handle missing images
        processed_content = latex_content
        
        # Check for image includes that might be missing
        if "\\includegraphics" in processed_content and "OCR_logo.jpg" in processed_content:
            print("Found image reference to OCR_logo.jpg - replacing with workaround")
            
            # Option 1: Comment out the problematic line
            processed_content = processed_content.replace(
                "\\includegraphics[width=0.5\\textwidth]{OCR_logo.jpg}",
                "% Image removed: OCR_logo.jpg not available\n\\vspace{2cm}"
            )
        
        # Write processed LaTeX content to file
        with tex_file_path.open("w", encoding="utf-8") as tex_file:
            tex_file.write(processed_content)
        
        # Compile LaTeX to PDF
        compile_command = [
            "pdflatex",
            "-interaction=nonstopmode",
            "-halt-on-error",
            "temp.tex"
        ]
        
        # Change to the temp directory for compilation
        os.chdir(str(temp_dir))
        
        # First run
        result = subprocess.run(
            compile_command,
            capture_output=True,
            text=True,
            check=False  # Don't raise exception on error
        )
        print(f"Return code: {result.returncode}")
        print(f"STDOUT: {result.stdout}")
        print(f"STDERR: {result.stderr}")
        
        if result.returncode != 0:
            print(f"LaTeX compilation error (first pass): {result.stderr}")
            # Check if the error is just the MiKTeX update warning
            if "So far, you have not checked for MiKTeX updates" in result.stderr and not "Fatal error" in result.stderr:
                print("Ignoring MiKTeX update warning and continuing compilation")
            else:
                # Continue anyway, sometimes the second pass resolves issues
                print("Continuing to second pass despite errors")
        
        # Second run for references
        result = subprocess.run(
            compile_command,
            capture_output=True,
            text=True,
            check=False  # Don't raise exception on error
        )
        
        if result.returncode != 0:
            print(f"LaTeX compilation error (second pass): {result.stderr}")
            # Check if the error is just the MiKTeX update warning
            if "So far, you have not checked for MiKTeX updates" in result.stderr and not "Fatal error" in result.stderr:
                print("Ignoring MiKTeX update warning")
        
        # Return to original directory
        os.chdir(original_dir)
        
        # Check if PDF was generated
        compiled_pdf_path = temp_dir / "temp.pdf"
        if not compiled_pdf_path.exists():
            print("No PDF was produced")
            # Try to run a direct check with the OS to ensure the file really doesn't exist
            # Sometimes file system operations can be asynchronous
            if os.path.isfile(str(compiled_pdf_path)):
                print("PDF found with direct OS check")
            else:
                return None
        
        # Move PDF to final location
        shutil.copy(str(compiled_pdf_path), str(final_pdf_path))
        
        # Return the relative path for storage in database
        # This path should be relative to the static folder for use with url_for
        result_path = f"generated_pdfs/{user_id_str}/{pdf_filename}"
        
        # Ensure we're back in the original directory before cleanup
        if os.getcwd() != str(original_dir):
            os.chdir(str(original_dir))
        
        # Clean up all temporary files after successful PDF generation
        try:
            print(f"Cleaning up temporary files in {temp_dir}")
            # First remove individual files
            for file_pattern in ["temp.*", "*.aux", "*.log", "*.out", "*.toc"]:
                for file_path in temp_dir.glob(file_pattern):
                    try:
                        if file_path.is_file():
                            file_path.unlink()
                            print(f"Removed temporary file: {file_path.name}")
                    except Exception as e:
                        print(f"Error removing file {file_path}: {e}")
            
            # Then remove the directory itself
            if temp_dir.exists():
                try:
                    temp_dir.rmdir()
                    print(f"Successfully removed temporary directory: {temp_dir}")
                except Exception as e:
                    print(f"Could not remove directory {temp_dir}: {e}")
        except Exception as cleanup_error:
            print(f"Error during file cleanup: {str(cleanup_error)}")
            # Continue even if cleanup fails, we don't want to lose the PDF
            
        # Schedule a full cleanup of orphaned temporary files
        try:
            # This will clean up any other temporary files that might have been missed
            cleanup_temp_latex_files()
        except Exception as e:
            print(f"Error during full cleanup: {e}")
        
        return result_path
    
    except Exception as e:
        print(f"Error in LaTeX compilation: {str(e)}")
        # Make sure we're back in the original directory
        if os.getcwd() != str(original_dir):
            os.chdir(str(original_dir))
        
        # Attempt cleanup even if compilation failed
        if temp_dir.exists():
            try:
                print(f"Cleaning up temporary files after error in {temp_dir}")
                # First remove individual files using a more robust pattern matching approach
                for file_pattern in ["temp.*", "*.aux", "*.log", "*.out", "*.toc"]:
                    for file_path in temp_dir.glob(file_pattern):
                        try:
                            if file_path.is_file():
                                file_path.unlink()
                                print(f"Removed temporary file: {file_path.name}")
                        except Exception as e:
                            print(f"Error removing file {file_path}: {e}")
                
                # Then remove the directory itself
                if temp_dir.exists():
                    try:
                        temp_dir.rmdir()
                        print(f"Successfully removed temporary directory after error: {temp_dir}")
                    except Exception as e:
                        print(f"Could not remove directory {temp_dir}: {e}")
            except Exception as cleanup_error:
                print(f"Error during cleanup after compilation failure: {str(cleanup_error)}")
            
            # Also attempt a full cleanup to catch any orphaned files
            try:
                cleanup_temp_latex_files()
            except Exception as e:
                print(f"Error during full cleanup after failure: {e}")
        
        return None
